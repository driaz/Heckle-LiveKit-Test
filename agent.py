"""Heckle v2 latency rig: fake game events -> Claude -> ElevenLabs -> Runway avatar.

Throwaway. Measures how long after a game event the narrator starts talking.
"""

import asyncio
import logging
import os
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
]
EVENT_INTERVAL_S = 10
# Runway caps sessions at 5 minutes. 12 events x 10 s is ~2 minutes; this is the hard stop.
AVATAR_MAX_DURATION_S = 240
AVATAR_READY_TIMEOUT_S = 60
# int16 peak above which the avatar's audio track counts as "speaking"
VOICE_PEAK_THRESHOLD = 1000

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


def summary_table(rows: list[dict], avatar_startup_s: float | None) -> str:
    def ms(row: dict, key: str) -> str:
        return f"{(row[key] - row['fired']) * 1000:.0f}" if key in row else "-"

    def avg(key: str) -> str:
        vals = [(r[key] - r["fired"]) * 1000 for r in rows if key in r]
        return f"{sum(vals) / len(vals):.0f}" if vals else "-"

    head = f"{'#':>2}  {'event':<52} {'LLM ms':>7} {'TTS ms':>7} {'voice ms':>8}"
    lines = [
        "",
        "Milliseconds after the event fired: LLM first token, TTS first audio frame,",
        "first audible audio on the avatar's track (what a viewer hears, lip-synced).",
        head,
        "-" * len(head),
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i:>2}  {r['event'][:52]:<52} {ms(r, 'llm'):>7} {ms(r, 'tts'):>7} {ms(r, 'voice'):>8}"
        )
    lines.append("-" * len(head))
    lines.append(f"{'':>2}  {'mean':<52} {avg('llm'):>7} {avg('tts'):>7} {avg('voice'):>8}")
    if avatar_startup_s is not None:
        lines.append(f"Avatar first video frame: {avatar_startup_s:.1f} s after avatar start")
    return "\n".join(lines)


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    logger.info("participant %s joined, starting avatar", participant.identity)

    narrator = Narrator()
    rows: list[dict] = []
    avatar_video_at: asyncio.Future[float] = asyncio.get_running_loop().create_future()
    watchers: set[asyncio.Task] = set()

    session = AgentSession(
        llm=anthropic.LLM(
            model="claude-opus-5-5",
            api_key=os.environ["HECKLE_ANTHROPIC_API_KEY"],
        ),
        tts=elevenlabs.TTS(
            model="eleven_v4_turbo",
            api_key=os.environ["ELEVENLABS_API_KEY"],  # plugin's own default is ELEVEN_API_KEY
        ),
    )
    # reads RUNWAYML_API_SECRET and LIVEKIT_* from the environment
    avatar = runway.AvatarSession(preset_id="game-character", max_duration=AVATAR_MAX_DURATION_S)

    async def watch_video(track: rtc.Track) -> None:
        stream = rtc.VideoStream(track)
        async for _ in stream:
            if not avatar_video_at.done():
                avatar_video_at.set_result(time.perf_counter())
            break
        await stream.aclose()

    async def watch_audio(track: rtc.Track) -> None:
        async for ev in rtc.AudioStream(track):
            cur = narrator.current
            if cur is None or "voice" in cur:
                continue
            if max(map(abs, ev.frame.data)) > VOICE_PEAK_THRESHOLD:
                cur["voice"] = time.perf_counter()

    @ctx.room.on("track_subscribed")
    def on_track(track: rtc.Track, pub: rtc.RemoteTrackPublication, p: rtc.RemoteParticipant):
        if p.identity != avatar.avatar_identity:
            return
        watch = watch_video if track.kind == rtc.TrackKind.KIND_VIDEO else watch_audio
        task = asyncio.create_task(watch(track))
        watchers.add(task)
        task.add_done_callback(watchers.discard)

    avatar_started = time.perf_counter()
    await avatar.start(session, room=ctx.room)
    await session.start(
        agent=narrator,
        room=ctx.room,
        # no mic, no STT, no chat input; the avatar publishes the audio, not the agent
        room_options=room_io.RoomOptions(audio_input=False, text_input=False, audio_output=False),
    )

    avatar_startup_s: float | None = None
    try:
        first_frame = await asyncio.wait_for(avatar_video_at, AVATAR_READY_TIMEOUT_S)
        avatar_startup_s = first_frame - avatar_started
        logger.info("avatar first video frame after %.1f s", avatar_startup_s)
    except asyncio.TimeoutError:
        logger.warning("no avatar video after %d s, firing events anyway", AVATAR_READY_TIMEOUT_S)

    printed = False

    async def print_summary() -> None:
        nonlocal printed
        if not printed and rows:
            printed = True
            logger.info(summary_table(rows, avatar_startup_s))

    ctx.add_shutdown_callback(print_summary)  # also covers the viewer leaving early

    for i, event in enumerate(EVENTS, 1):
        row = {"event": event, "fired": time.perf_counter()}
        rows.append(row)
        narrator.current = row
        logger.info("event %d/%d fired: %s", i, len(EVENTS), event)
        await session.generate_reply(user_input=f"The player {event}.")
        logger.info(
            "event %d: llm +%s ms, tts +%s ms, avatar voice +%s ms",
            i,
            *(f"{(row[k] - row['fired']) * 1000:.0f}" if k in row else "-" for k in ("llm", "tts", "voice")),
        )
        await asyncio.sleep(max(0.0, EVENT_INTERVAL_S - (time.perf_counter() - row["fired"])))

    narrator.current = None
    await print_summary()
    await session.aclose()  # also ends the Runway session
    ctx.shutdown("script finished")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
