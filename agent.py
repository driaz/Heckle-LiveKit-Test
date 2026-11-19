"""Heckle v2 latency rig: fake game events -> Claude -> ElevenLabs -> Runway avatar.

Throwaway. Measures how long after a game event the narrator starts talking.
"""

import asyncio
import logging
import math
import os
import statistics
import time

from livekit import rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.voice import room_io
from livekit.plugins import anthropic, elevenlabs, runway

logger = logging.getLogger("heckle")

EVENTS = [
    "fell off the ledge for the fifth time",
    "died to the same spike pit again",
    "spent 40 seconds lining up an easy jump",
    "walked straight past the checkpoint",
    "jumped into a wall three times in a row",
    "got killed by the slowest enemy in the game",
    "collected zero coins in the bonus room",
    "paused the game to read the controls",
    "missed a moving platform that wasn't moving",
    "finally cleared the first gap, then fell in the second",
    "stood still for 20 seconds doing nothing",
    "died within two seconds of respawning",
    "ran the wrong way for a full minute",
    "bounced off the same spring into the same ceiling",
    "fell through a gap one tile wide",
    "used the only extra life in the tutorial",
    "hit the checkpoint, then walked back into the lava",
    "tried to jump on a spike to see what happens",
    "let the timer run out one step from the exit",
    "celebrated early and fell off the victory platform",
]
# Runway caps a session at 5 minutes. 20 events take about 4 (measured: ~12 s each), so they run in
# one avatar session; no new event fires after the budget, so a reply is never cut off by the cap.
AVATAR_MAX_DURATION_S = 295
EVENT_BUDGET_S = 270
AVATAR_READY_TIMEOUT_S = 60
# The next event fires this long after the avatar goes quiet.
GAP_AFTER_SPEECH_S = 2.0
# int16 peak above which a frame of the avatar's audio track counts as speech
VOICE_PEAK_THRESHOLD = 1000
# A reply's voice starts at the first loud frame that follows at least this much quiet.
VOICE_ONSET_SILENCE_S = 0.3
# The avatar can't voice a reply sooner than this after TTS produced its first audio.
MIN_TTS_TO_VOICE_S = 0.1
COLUMNS = ("llm", "tts", "voice")

INSTRUCTIONS = (
    "You are the narrator of a platformer game, and you are sarcastic and merciless. "
    "Each message describes something the player just did. Roast them for it. "
    "Reply with one or two short sentences of plain spoken text. No emoji, no stage directions."
)


class Narrator(Agent):
    """Stamps the first LLM token and first TTS audio frame of each reply."""

    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)
        self.current: dict | None = None  # timings of the event being answered

    def _stamp(self, key: str) -> None:
        if self.current is not None and key not in self.current:
            self.current[key] = time.perf_counter()

    async def llm_node(self, chat_ctx, tools, model_settings):
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            self._stamp("llm")
            yield chunk

    async def tts_node(self, text, model_settings):
        async for frame in Agent.default.tts_node(self, text, model_settings):
            self._stamp("tts")
            yield frame


def offset_ms(row: dict, key: str) -> float | None:
    return (row[key] - row["fired"]) * 1000 if key in row else None


def distrust(row: dict) -> str | None:
    """Why this row's avatar voice time can't be trusted, or None if it can."""
    if "voice" not in row:
        return "no avatar voice detected"
    if row.get("audio_at_fire"):
        return "avatar audio still playing when the event fired"
    if "tts" not in row or row["voice"] - row["tts"] < MIN_TTS_TO_VOICE_S:
        return "avatar voice earlier than TTS allows"
    return None


def summary_table(rows: list[dict], avatar_startup_s: float | None) -> str:
    def cell(value: float | None) -> str:
        return "-" if value is None else f"{value:.0f}"

    head = f"{'#':>2}  {'event':<50} {'LLM ms':>7} {'TTS ms':>7} {'voice ms':>9}"
    rule = "-" * len(head)
    lines = [
        "",
        "SUMMARY. Milliseconds after the event fired: LLM first token, TTS first audio frame,",
        "first avatar audio (what a viewer hears, lip-synced). * = voice time not trusted.",
        head,
        rule,
    ]
    notes = []
    for i, r in enumerate(rows, 1):
        reason = distrust(r)
        if reason:
            notes.append(f"* row {i}: {reason}; left out of the voice stats")
        voice = cell(offset_ms(r, "voice")) + ("*" if reason else " ")
        llm, tts = cell(offset_ms(r, "llm")), cell(offset_ms(r, "tts"))
        lines.append(f"{i:>2}  {r['event'][:50]:<50} {llm:>7} {tts:>7} {voice:>9}")
    lines.append(rule)

    values = {
        key: sorted(
            v
            for r in rows
            if (v := offset_ms(r, key)) is not None and not (key == "voice" and distrust(r))
        )
        for key in COLUMNS
    }
    stats = {
        "median": lambda v: statistics.median(v),
        "p90 (nearest rank)": lambda v: v[math.ceil(0.9 * len(v)) - 1],
        "max": lambda v: v[-1],
        "rows counted": lambda v: len(v),
    }
    for name, fn in stats.items():
        llm, tts, voice = (cell(fn(values[k])) if values[k] else "-" for k in COLUMNS)
        lines.append(f"{'':>2}  {name:<50} {llm:>7} {tts:>7} {voice + ' ':>9}")
    lines += notes
    if len(rows) < len(EVENTS):
        lines.append(f"Only {len(rows)} of {len(EVENTS)} events fired")
    if avatar_startup_s is not None:
        lines.append(f"Avatar first video frame: {avatar_startup_s:.1f} s after avatar start")
    return "\n".join(lines)


def new_agent_session() -> AgentSession:
    return AgentSession(
        llm=anthropic.LLM(
            model="claude-opus-5-5",
            api_key=os.environ["HECKLE_ANTHROPIC_API_KEY"],
        ),
        tts=elevenlabs.TTS(
            model="eleven_v4_turbo",
            voice_id="E95b3lkMWHDsKeHJaIcY",
            api_key=os.environ["ELEVENLABS_API_KEY"],  # plugin's own default is ELEVEN_API_KEY
        ),
    )


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    logger.info("participant %s joined, starting avatar", participant.identity)

    rows: list[dict] = []
    avatar_startup_s: float | None = None
    printed = False

    async def print_summary() -> None:
        nonlocal printed
        if not printed and rows:
            printed = True
            logger.info(summary_table(rows, avatar_startup_s))

    ctx.add_shutdown_callback(print_summary)  # also covers the viewer leaving early

    narrator = Narrator()
    session = new_agent_session()
    # reads RUNWAYML_API_SECRET and LIVEKIT_* from the environment
    avatar = runway.AvatarSession(preset_id="cat-character", max_duration=AVATAR_MAX_DURATION_S)
    avatar_video_at: asyncio.Future[float] = asyncio.get_running_loop().create_future()
    watchers: set[asyncio.Task] = set()
    last_loud = float("-inf")  # when the avatar's audio track was last audible

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
            cur = narrator.current
            # Leftover audio from the previous line is continuous, so it never follows quiet;
            # and nothing before this event's TTS audio can be this event's reply.
            if cur is not None and "voice" not in cur and "tts" in cur and quiet_before:
                cur["voice"] = now

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

    ctx.room.on("track_subscribed", on_track)
    try:
        avatar_started = time.perf_counter()
        await avatar.start(session, room=ctx.room)
        await session.start(
            agent=narrator,
            room=ctx.room,
            # no mic, no STT, no chat input; the avatar publishes the audio, not the agent
            room_options=room_io.RoomOptions(
                audio_input=False, text_input=False, audio_output=False
            ),
        )
        try:
            first_frame = await asyncio.wait_for(avatar_video_at, AVATAR_READY_TIMEOUT_S)
            avatar_startup_s = first_frame - avatar_started
            logger.info("avatar first video frame after %.1f s", avatar_startup_s)
        except asyncio.TimeoutError:
            logger.warning("no avatar video after %d s, firing anyway", AVATAR_READY_TIMEOUT_S)

        for event in EVENTS:
            now = time.perf_counter()
            if now - avatar_started > EVENT_BUDGET_S:
                logger.warning("out of session time, stopping after %d events", len(rows))
                break
            row = {
                "event": event,
                "fired": now,
                "audio_at_fire": now - last_loud < VOICE_ONSET_SILENCE_S,
            }
            rows.append(row)
            narrator.current = row
            logger.info("event %d/%d fired: %s", len(rows), len(EVENTS), event)
            await session.generate_reply(user_input=f"The player {event}.")
            # The avatar lags the agent's own idea of playout, so pace off its audio track:
            # wait for the reply to be heard, then for the avatar to stay quiet for the gap.
            await wait_until(lambda: "voice" in row, timeout=5)
            await wait_until(
                lambda: time.perf_counter() - last_loud >= GAP_AFTER_SPEECH_S, timeout=30
            )
            logger.info(
                "event %d: llm +%s ms, tts +%s ms, avatar voice +%s ms%s",
                len(rows),
                *(f"{v:.0f}" if (v := offset_ms(row, k)) is not None else "-" for k in COLUMNS),
                f" (not trusted: {reason})" if (reason := distrust(row)) else "",
            )
    except RuntimeError as e:
        # generate_reply raises this once the viewer has left and the session has closed
        logger.warning("run ended early: %s", e)
    finally:
        narrator.current = None
        await print_summary()
        await session.aclose()
        await avatar.aclose()  # ends the Runway session
        for task in watchers:
            task.cancel()
    ctx.shutdown("script finished")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
