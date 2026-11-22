"""Heckle v2 narrator: game events and the player's voice -> Claude -> ElevenLabs -> Runway avatar.

The game joins a room and publishes short JSON events on the "heckle.event" topic, and the player's
mic if they allow it. The narrator says one thing at a time: events that arrive while it is busy
are merged or dropped (see Inbox), and it does not listen while it is speaking.
"""

import asyncio
import json
import logging
import os
import time

from livekit import rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.voice import room_io
from livekit.plugins import anthropic, elevenlabs, runway

logger = logging.getLogger("heckle")

# The narrator LLM. Set HECKLE_LLM_MODEL to switch, e.g. claude-haiku-5-5.
LLM_MODEL = os.environ.get("HECKLE_LLM_MODEL") or "claude-opus-5-5"
# Haiku runs long, so it gets a stricter length rule and a hard cap on output tokens.
# 60 tokens is about 30 spoken words. Opus keeps the prompt as it is and has no cap.
IS_HAIKU = "haiku" in LLM_MODEL
MAX_REPLY_TOKENS = 60 if IS_HAIKU else None
# The Runway Character. Set HECKLE_RUNWAY_AVATAR_ID to a custom avatar's ID; unset or empty is the cat.
RUNWAY_AVATAR_ID = os.environ.get("HECKLE_RUNWAY_AVATAR_ID", "").strip()
RUNWAY_PRESET_ID = "cat-character"
SENTENCE_END = (".", "!", "?", "…", '"', "'", ")")

EVENT_TOPIC = "heckle.event"
MAX_EVENT_BYTES = 512
MAX_FIELD_CHARS = 60
MAX_LEVEL_GUIDE_CHARS = 4000

# Runway caps a session at 5 minutes. No reply starts after the budget, so none is cut off by the
# cap; the job then ends and the game joins a fresh room for a new session.
AVATAR_MAX_DURATION_S = 295
EVENT_BUDGET_S = 270
AVATAR_READY_TIMEOUT_S = 60
# The next reply may start once the avatar has been quiet for this long.
GAP_AFTER_SPEECH_S = 1.0
# Server-side voice detection ends the player's turn after this much silence.
PLAYER_SILENCE_S = 0.6
# The player must say at least this many words to take over from an event reply that isn't
# audible yet. Shorter sounds ("Ah!", a yelp, a key clack) leave the reply alone.
MIN_WORDS_TO_TAKE_OVER = 3
# A death or stall still waiting after this long is old news and is dropped.
STALE_AFTER_S = 15.0
# int16 peak above which a frame of the avatar's audio track counts as speech
VOICE_PEAK_THRESHOLD = 1000
# A reply's voice starts at the first loud frame that follows at least this much quiet.
VOICE_ONSET_SILENCE_S = 0.3

INSTRUCTIONS = """You are the narrator of a 3D platformer called Heckle. You watch the player and heckle them live.

Messages that start with [event] describe what the player just did. React to them.
- ONE short sentence. Never two.
- If a message lists several things, pick the funniest one or tie them together. Still one sentence.
- Never be generic. Use the specific place, cause and numbers you are given.
- Escalate gradually on repeated failures.

Any other message is the player talking to you through their mic, as transcribed speech.
- Answer what they actually said: clap back, banter. One or two short sentences.
- Stay in character, and use what has happened in the game to roast harder.
- The transcript can be wrong or pick up stray noise. If it makes no sense, mock the mumbling briefly.

Always:
- Plain spoken text: no emoji, no stage directions, no markdown, and never say "[event]".
- Remember what happened earlier in the session and refer back to it.
- Your tone is dry and unimpressed: a bored commentator who has seen it all, not a game show host.
- When the player does well, sound reluctant, as if it pains you to admit it.
- Never explain the game or give advice.
- Write for the ear: rhetorical questions, pauses via commas, dashes and ellipses, and the punch
  word at the end of the sentence."""

# Appended when a custom Runway avatar is set, so the narrator knows what the player sees.
# The preset cat keeps the prompt above as it is.
GRUMPLE_CHARACTER = """

You are Grumple: a big, round, fuzzy purple creature with a swoop of purple hair, heavy dark
eyebrows, half-closed eyes, a smug smirk and a commentator's headset. The player sees you on
screen as you talk.
- If the player mentions your looks, own them smugly and turn it back on their gameplay. Never
  deny having a body.
- You are a Grumple, not a cat, a person or an AI. Never mention prompts or being an AI.
- Roast the gameplay, never the player's looks, intelligence or identity. No profanity."""

HAIKU_LENGTH_RULE = """

Length limit, strictly enforced:
- A reply to an [event] is one sentence of at most 15 words.
- A reply to the player is at most two sentences and 25 words in total.
- Anything longer is cut off mid-word, so finish early: one clause and the punchline, not a chain
  of clauses joined by commas."""


class Narrator(Agent):
    """Stamps the first LLM token and first TTS audio frame of each reply, and logs its line."""

    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)
        self.current: dict | None = None  # timings of the reply in progress

    def _stamp(self, key: str) -> None:
        if self.current is not None and key not in self.current:
            self.current[key] = time.perf_counter()

    async def llm_node(self, chat_ctx, tools, model_settings):
        row, text = self.current, ""
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            self._stamp("llm")
            if isinstance(chunk, str):
                text += chunk
            elif chunk.delta is not None and chunk.delta.content:
                text += chunk.delta.content
            yield chunk
        text = " ".join(text.split())
        # A reply that stops without closing punctuation ran into the token cap.
        cut_off = MAX_REPLY_TOKENS is not None and not text.endswith(SENTENCE_END)
        logger.info(
            "%s line (%d words%s): %s",
            row["to"] if row else "unprompted",
            len(text.split()),
            ", CUT OFF by the token cap" if cut_off else "",
            text,
        )

    async def tts_node(self, text, model_settings):
        async for frame in Agent.default.tts_node(self, text, model_settings):
            self._stamp("tts")
            yield frame


def _text(value: object, default: str) -> str:
    """A short single-line string from untrusted input."""
    if not isinstance(value, str):
        return default
    return " ".join(value.split())[:MAX_FIELD_CHARS] or default


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0 <= value < 1e6 else None


def describe(ev: dict) -> str | None:
    """One sentence for the LLM from a game event, or None for an event we don't know.

    Events (all fields but "t" optional):
      {"t": "death", "cause": "fall" | <hazard name>, "at": <area>, "n": <deaths so far>,
       "here": <deaths in this area>, "gap": <seconds since the previous death, if quick>}
      {"t": "stall", "at": <area>, "secs": <seconds standing still>}
      {"t": "checkpoint", "name": <checkpoint>, "n": <deaths so far>, "secs": <seconds played>}
      {"t": "finish", "n": <deaths>, "secs": <seconds played>, "stars": "7/10"}
    """
    kind = ev.get("t")
    place = _text(ev.get("at"), "")
    deaths, secs = _number(ev.get("n")), _number(ev.get("secs"))

    if kind == "death":
        cause = _text(ev.get("cause"), "fall")
        where = place or "the course"
        line = f"fell off {where}" if cause == "fall" else f"was killed by {cause} at {where}"
        if deaths:
            line += f", death number {deaths:.0f}"
        if (here := _number(ev.get("here"))) and here >= 2:
            line += f", {here:.0f} deaths at this spot"
        if (gap := _number(ev.get("gap"))) is not None:
            line += f", only {gap:.0f} seconds after the last death"
        merged = ev.get("_merged", 1)
        if merged > 1:
            return f"The player died {merged} times in a row; the latest: {line}."
        return f"The player {line}."

    if kind == "stall" and secs:
        where = f" at {place}" if place else ""
        return f"The player has been standing still for {secs:.0f} seconds{where}."

    if kind == "checkpoint":
        line = f"The player reached the {_text(ev.get('name'), 'next')} checkpoint"
        if deaths is not None:
            line += f" after {deaths:.0f} deaths"
        if secs:
            line += f", {secs:.0f} seconds in"
        return line + "."

    if kind == "finish":
        line = "The player finished the course"
        if secs:
            line += f" in {secs:.0f} seconds"
        if deaths is not None:
            line += f" with {deaths:.0f} deaths"
        if stars := _text(ev.get("stars"), ""):
            line += f" and {stars} stars"
        return line + "."

    return None


class Inbox:
    """Holds what happened while the narrator was busy: at most one event per kind.

    A newer event replaces an older one of its kind (deaths keep a count), anything newer cancels a
    waiting stall, and deaths and stalls that wait too long are dropped. take() hands over
    everything left as one batch, so a backlog becomes a single reply.
    """

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._items: dict[str, dict] = {}  # insertion order = order of each kind's latest event
        self._wake = asyncio.Event()
        self._closed = False

    def put(self, ev: dict) -> None:
        kind = ev["t"]
        previous = self._items.pop(kind, None)
        if kind != "stall":
            self._items.pop("stall", None)  # the player is doing something else now
        merged = previous["_merged"] + 1 if previous and kind == "death" else 1
        self._items[kind] = {**ev, "_merged": merged, "_at": self._clock()}
        self._wake.set()

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    def _drain(self) -> list[dict]:
        now = self._clock()
        items, self._items = list(self._items.values()), {}
        return [
            ev
            for ev in items
            if ev["t"] not in ("death", "stall") or now - ev["_at"] <= STALE_AFTER_S
        ]

    async def take(self, timeout: float, ready=None) -> list[dict] | None:
        """The next batch of events, or None once closed or after `timeout` seconds.

        `ready` is awaited once there is something to say and before it is handed over, so events
        keep merging until the narrator is actually free.
        """
        deadline = self._clock() + timeout
        while not self._closed:
            if self._items:
                if ready is not None:
                    await ready()
                if batch := self._drain():
                    return batch
                continue
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), deadline - self._clock())
            except asyncio.TimeoutError:
                return None
        return None


def parse_event(data: bytes) -> dict | None:
    if len(data) > MAX_EVENT_BYTES:
        return None
    try:
        ev = json.loads(data)
    except ValueError:
        return None
    if not isinstance(ev, dict) or describe(ev) is None:
        return None
    return {k: v for k, v in ev.items() if not k.startswith("_")}


def new_agent_session() -> AgentSession:
    return AgentSession(
        llm=anthropic.LLM(
            model=LLM_MODEL,
            api_key=os.environ["HECKLE_ANTHROPIC_API_KEY"],
            **({"max_tokens": MAX_REPLY_TOKENS} if MAX_REPLY_TOKENS else {}),
        ),
        stt=elevenlabs.STT(
            model="scribe_v2_realtime",
            language_code="en",
            server_vad={"vad_silence_threshold_secs": PLAYER_SILENCE_S},
            api_key=os.environ["ELEVENLABS_API_KEY"],
        ),
        turn_handling={
            # the STT's own voice detection decides when the player has finished
            "turn_detection": "stt",
            # Scribe has already waited out the silence; don't wait again before answering.
            "endpointing": {"min_delay": 0.0},
            # The player can't cut the narrator off once it is audible, and the mic is ignored
            # while it speaks, so its own voice from the player's speakers is never transcribed.
            # (An event reply that isn't audible yet is the exception; see on_player_speech.)
            "interruption": {"enabled": False, "min_words": MIN_WORDS_TO_TAKE_OVER},
        },
        tts=elevenlabs.TTS(
            model="eleven_v4_turbo",
            voice_id="E95b3lkMWHDsKeHJaIcY",
            api_key=os.environ["ELEVENLABS_API_KEY"],  # plugin's own default is ELEVEN_API_KEY
        ),
    )


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    try:
        player = await ctx.wait_for_participant()
    except RuntimeError:
        logger.info("room closed before a player joined")  # e.g. the page was reloaded
        return
    avatar_name = f"custom {RUNWAY_AVATAR_ID}" if RUNWAY_AVATAR_ID else f"preset {RUNWAY_PRESET_ID}"
    logger.info(
        "player %s joined, starting avatar %s; narrator model %s",
        player.identity, avatar_name, LLM_MODEL,
    )

    # The game's token endpoint puts a description of the level in the player's metadata.
    instructions = (
        INSTRUCTIONS
        + (GRUMPLE_CHARACTER if RUNWAY_AVATAR_ID else "")
        + (HAIKU_LENGTH_RULE if IS_HAIKU else "")
    )
    if guide := (player.metadata or "")[:MAX_LEVEL_GUIDE_CHARS].strip():
        instructions += f"\n\nThe course, in order:\n{guide}"

    narrator = Narrator(instructions)
    session = new_agent_session()
    # reads RUNWAYML_API_SECRET and LIVEKIT_* from the environment
    # the plugin rejects avatar_id and preset_id together
    which = {"avatar_id": RUNWAY_AVATAR_ID} if RUNWAY_AVATAR_ID else {"preset_id": RUNWAY_PRESET_ID}
    avatar = runway.AvatarSession(**which, max_duration=AVATAR_MAX_DURATION_S)
    avatar_video_at: asyncio.Future[float] = asyncio.get_running_loop().create_future()
    watchers: set[asyncio.Task] = set()
    last_loud = float("-inf")  # when the avatar's audio track was last audible
    rows: list[dict] = []  # timings of replies whose voice hasn't been heard yet, oldest first

    def start_timing(to: str) -> dict:
        """Time a new reply. Claude and TTS stamp it via the narrator; the avatar's voice is
        matched to it later, even if another reply has started being timed by then."""
        row = {"to": to, "fired": time.perf_counter()}
        narrator.current = row
        rows.append(row)
        del rows[:-8]  # replies that never reach TTS would otherwise pile up
        return row
    inbox = Inbox()

    def on_data(packet: rtc.DataPacket) -> None:
        # From the player, or from the server API (no participant), which needs the API secret.
        if packet.topic != EVENT_TOPIC:
            return
        if packet.participant is not None and packet.participant.identity != player.identity:
            return
        ev = parse_event(packet.data)
        if ev is None:
            logger.warning("ignored a malformed event (%d bytes)", len(packet.data))
            return
        inbox.put(ev)

    def on_participant_left(p: rtc.RemoteParticipant) -> None:
        if p.identity == player.identity:
            logger.info("player left")
            inbox.close()

    async def watch_video(track: rtc.Track) -> None:
        stream = rtc.VideoStream(track)
        async for _ in stream:
            if not avatar_video_at.done():
                avatar_video_at.set_result(time.perf_counter())
            break
        await stream.aclose()

    async def watch_audio(track: rtc.Track) -> None:
        nonlocal last_loud
        async for ev in rtc.AudioStream(track):
            if max(map(abs, ev.frame.data)) <= VOICE_PEAK_THRESHOLD:
                continue
            now = time.perf_counter()
            quiet_before = now - last_loud >= VOICE_ONSET_SILENCE_S
            last_loud = now
            # Leftover audio from the previous line is continuous, so it never follows quiet.
            # The voice belongs to the oldest reply whose TTS audio exists; replies before it
            # were dropped or never spoken.
            if not quiet_before:
                continue
            spoken = next((i for i, r in enumerate(rows) if "tts" in r), None)
            if spoken is None:
                continue
            row = rows[spoken]
            del rows[: spoken + 1]
            row["voice"] = now
            logger.info(
                "%s reply: llm +%.0f ms, tts +%.0f ms, avatar voice +%.0f ms",
                row["to"],
                *((row[k] - row["fired"]) * 1000 for k in ("llm", "tts", "voice")),
            )

    def on_track(track: rtc.Track, pub: rtc.RemoteTrackPublication, p: rtc.RemoteParticipant):
        if p.identity != avatar.avatar_identity:
            return
        watch = watch_video if track.kind == rtc.TrackKind.KIND_VIDEO else watch_audio
        task = asyncio.create_task(watch(track))
        watchers.add(task)
        task.add_done_callback(watchers.discard)

    async def wait_until(condition, timeout: float) -> bool:
        deadline = time.perf_counter() + timeout
        while not condition():
            if time.perf_counter() > deadline:
                return False
            await asyncio.sleep(0.05)
        return True

    event_reply = None  # the SpeechHandle of the event reply in progress, if any

    def event_reply_pending() -> bool:
        return event_reply is not None and not event_reply.done() and not event_reply.interrupted

    def on_player_speech(ev) -> None:
        if not ev.transcript.strip():
            return
        # The player's voice wins over an event reply that isn't audible yet: drop that reply and
        # answer the player. The event stays in the chat history, so the answer can still use it.
        enough_words = len(ev.transcript.split()) >= MIN_WORDS_TO_TAKE_OVER
        if enough_words and event_reply_pending() and session.agent_state != "speaking":
            logger.info("player spoke; dropping the event reply in progress")
            event_reply.interrupt()
        if not ev.is_final:
            return
        logger.info("player said: %s", ev.transcript)
        if not event_reply_pending():  # otherwise this goes unanswered; keep the event's timings
            # Latency for speech is counted from the end of the player's turn.
            start_timing("speech")

    def on_agent_state(ev) -> None:
        # Once an event reply is audible it can no longer be dropped, and the mic is ignored
        # until it finishes, so the narrator never hears itself.
        if ev.new_state == "speaking" and event_reply_pending():
            event_reply.allow_interruptions = False

    def narrator_free() -> bool:
        return (
            session.agent_state in ("listening", "idle")
            and session.user_state != "speaking"
            and time.perf_counter() - last_loud >= GAP_AFTER_SPEECH_S
        )

    async def until_narrator_free() -> None:
        # The avatar lags the agent's own idea of playout, so this also watches its audio track.
        await wait_until(narrator_free, timeout=30)

    session.on("user_input_transcribed", on_player_speech)
    session.on("agent_state_changed", on_agent_state)
    ctx.room.on("data_received", on_data)
    ctx.room.on("participant_disconnected", on_participant_left)
    ctx.room.on("track_subscribed", on_track)
    replies = 0
    try:
        avatar_started = time.perf_counter()
        await avatar.start(session, room=ctx.room)
        await session.start(
            agent=narrator,
            room=ctx.room,
            # the player's mic in, no chat input; the avatar publishes the audio, not the agent
            room_options=room_io.RoomOptions(
                audio_input=True, text_input=False, audio_output=False
            ),
        )
        try:
            first_frame = await asyncio.wait_for(avatar_video_at, AVATAR_READY_TIMEOUT_S)
            logger.info("avatar first video frame after %.1f s", first_frame - avatar_started)
        except asyncio.TimeoutError:
            logger.warning("no avatar video after %d s, narrating anyway", AVATAR_READY_TIMEOUT_S)

        while True:
            budget = EVENT_BUDGET_S - (time.perf_counter() - avatar_started)
            batch = await inbox.take(budget, until_narrator_free) if budget > 0 else None
            if batch is None or time.perf_counter() - avatar_started > EVENT_BUDGET_S:
                break
            prompt = "[event] " + " ".join(describe(ev) for ev in batch)
            row = start_timing("event")
            replies += 1
            logger.info("reply %d to: %s", replies, prompt)
            # Droppable until it becomes audible; see on_player_speech and on_agent_state.
            event_reply = session.generate_reply(user_input=prompt, allow_interruptions=True)
            await event_reply
            if event_reply.interrupted:
                if row in rows:
                    rows.remove(row)  # dropped for the player; it will never be voiced
            else:
                # Give the avatar a moment to start voicing it, so the next check sees it speaking.
                await wait_until(lambda: "voice" in row, timeout=5)
    except RuntimeError as e:
        # generate_reply raises this once the player has left and the session has closed
        logger.warning("session ended early: %s", e)
    finally:
        narrator.current = None
        logger.info("ending after %d event replies", replies)
        await session.aclose()
        await avatar.aclose()  # ends the Runway session
        for task in watchers:
            task.cancel()
    ctx.shutdown("narrator session finished")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
