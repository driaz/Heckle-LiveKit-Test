# Heckle v2 latency rig

## Your steps

1. Make sure the worker is running (see "Run the worker") and has logged `registered worker`.
2. Open <https://agents-playground.livekit.io>, sign in with your LiveKit Cloud account and pick the
   same project the worker's `LIVEKIT_URL` points at.
3. Click **Connect**. Leave the mic off; the narrator doesn't listen.
4. The avatar appears after a few seconds, then heckles a fake event every ~10 s for about 2 minutes.
5. Read the summary table in the worker's log when it finishes (or when you disconnect).

Each connect is one run and one Runway session. Reconnect to run again.

## What this is

A throwaway test of the Heckle v2 narrator stack, to measure event-to-voice lag:

fake game event → Claude Opus 5.5 → ElevenLabs v4 Turbo → Runway Characters avatar (preset `game-character`)

There is no speech-to-text and no player mic. `agent.py` waits for a participant, starts the avatar,
then fires 12 scripted events through `generate_reply`. Per event it logs, in ms after the event fired:

| Column | Meaning |
| --- | --- |
| LLM ms | first token from Claude |
| TTS ms | first audio frame from ElevenLabs |
| voice ms | first audible audio on the avatar's published track, which is what a viewer hears |

The Runway plugin exposes no per-utterance video event, so "voice ms" is measured by the worker
subscribing to the avatar's audio track (the avatar publishes audio and video in sync). The time to
the avatar's first video frame is reported once per session. Viewer-side network and playout delay
are not included.

Runway caps sessions at 5 minutes: the script takes about 2 minutes and the session is created with
`max_duration=240` as a hard stop.

## Run the worker

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python agent.py dev
```

Environment variables:

| Variable | Used by |
| --- | --- |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | worker, and the Runway plugin to let the avatar join |
| `HECKLE_ANTHROPIC_API_KEY` | passed to the Anthropic plugin as `api_key=` |
| `ELEVENLABS_API_KEY` | passed to the ElevenLabs plugin as `api_key=` (its own default name is `ELEVEN_API_KEY`) |
| `RUNWAYML_API_SECRET` | read by the Runway plugin directly |

Network: the worker needs the LiveKit project host, `api.anthropic.com`, `api.elevenlabs.io` and
`api.dev.runwayml.com`.
