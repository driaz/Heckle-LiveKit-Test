# Heckle v2 latency rig

## Your steps

The worker is deployed to LiveKit Cloud, so there is nothing to start. From your phone:

1. Open <https://agents-playground.livekit.io> in the browser and sign in with your LiveKit Cloud account.
2. Pick the `heckle-o2pxy34d` project and tap **Connect**. Mute the mic; the narrator doesn't listen.
3. The avatar appears after a few seconds (longer on a cold start) and heckles 20 fake events. Stay
   connected until it leaves, about 4.5 minutes.
4. The summary table is in the agent's logs, not on the phone: run `lk agent logs` afterwards.

Each connect is one run and one Runway session. Disconnect and reconnect to run again.

## What this is

A throwaway test of the Heckle v2 narrator stack, to measure event-to-voice lag:

fake game event → Claude Opus 5.5 → ElevenLabs v4 Turbo → Runway Characters avatar (preset `cat-character`, the cat)

There is no speech-to-text and no player mic. `agent.py` waits for a participant, starts the avatar,
then fires 20 scripted events through `generate_reply`. The next event fires 2 s after the avatar
stops speaking, so the narrator never talks over itself. Per event it logs, in ms after the event
fired:

| Column | Meaning |
| --- | --- |
| LLM ms | first token from Claude |
| TTS ms | first audio frame from ElevenLabs |
| voice ms | first audible audio on the avatar's published track, which is what a viewer hears |

The Runway plugin exposes no per-utterance video event, so "voice ms" is measured by the worker
subscribing to the avatar's audio track (the avatar publishes audio and video in sync). The time to
the avatar's first video frame is reported once per session. Viewer-side network and playout delay
are not included.

The summary gives median, p90 and max per column. A reply's voice time only counts if the avatar's
audio starts after a stretch of quiet and after that reply's TTS audio exists; rows that fail this
are marked `*` with the reason and left out of the voice stats.

Runway caps sessions at 5 minutes. 20 events take about 4 (roughly 12 s each), so they run in one
session created with `max_duration=295`. No new event fires after 270 s, so a slow run reports fewer
events instead of having a reply cut off.

## Deploy

The agent runs on LiveKit Cloud (agent `CA_mGXcTcrKJGPB`, region `us-east`), configured by
`livekit.toml` and the `Dockerfile`. The `lk` CLI reads `LIVEKIT_URL`, `LIVEKIT_API_KEY` and
`LIVEKIT_API_SECRET` from the environment. Run these from the repo root.

Redeploy after a code change:

```bash
lk agent deploy
```

Check that it is running, and read its logs (including the summary table):

```bash
lk agent status
```

```bash
lk agent logs
```

Secrets live in LiveKit Cloud, never in the repo. To change one:

```bash
lk agent update-secrets --secrets "ELEVENLABS_API_KEY=<value>"
```

| Secret | Used by |
| --- | --- |
| `HECKLE_ANTHROPIC_API_KEY` | passed to the Anthropic plugin as `api_key=` |
| `ELEVENLABS_API_KEY` | passed to the ElevenLabs plugin as `api_key=` (its own default name is `ELEVEN_API_KEY`) |
| `RUNWAYML_API_SECRET` | read by the Runway plugin directly |

`LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` are injected by LiveKit Cloud.

## Run locally instead

Needs the six variables above in your shell and a network that allows WebRTC. Stop the cloud agent
first or both will compete for the same rooms.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python agent.py dev
```
