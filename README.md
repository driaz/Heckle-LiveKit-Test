# Heckle v2 narrator agent

The narrator for [Heckle](https://github.com/driaz/Heckle), running as a LiveKit agent:

game event → Claude Opus 5.5 → ElevenLabs v4 Turbo → Runway Characters avatar (preset `cat-character`, the cat)

This repo started as a latency rig that fired 20 scripted events. Those results are in
[RESULTS.md](RESULTS.md). The agent now takes real events from the game instead.

## How it works

The game joins a new LiveKit room on page load. LiveKit dispatches this agent to the room; it
starts the avatar straight away (about 6 seconds to the first video frame) and then waits for
events. There is no speech-to-text and no player mic.

Events are short JSON messages on the data topic `heckle.event`, sent by the player:

| Event | Example |
| --- | --- |
| Death | `{"t":"death","cause":"fall","at":"The Wobbly Bridge","n":4,"here":3,"gap":2.1}` |
| Stall | `{"t":"stall","at":"Start Island","secs":23}` |
| Checkpoint | `{"t":"checkpoint","name":"Crystal Gauntlet","n":3,"secs":95}` |
| Finish | `{"t":"finish","n":12,"secs":301,"stars":"7/10"}` |

`cause` is `fall` or a hazard's name, `n` is deaths so far, `here` is deaths in that area, and
`gap` is the seconds since the previous death when it was under 5. Every field except `t` is
optional. Messages over 512 bytes or of an unknown kind are ignored.

The level description (each area's name and what it is) arrives once, in the player's participant
metadata, which the game's token endpoint sets. It is appended to the narrator's instructions.

### Not talking over itself

The agent answers one batch at a time. It starts the next reply only after the avatar's audio
track has been quiet for 1 second. Events that arrive in the meantime wait in an inbox that keeps
at most one event per kind:

- a newer event replaces an older one of the same kind; deaths keep a count ("died 3 times in a row")
- any newer event cancels a waiting stall
- deaths and stalls that have waited more than 15 seconds are dropped; checkpoints and the finish
  are kept

Whatever is left becomes a single reply.

### Session length

Runway caps a session at 5 minutes. No reply starts after 270 seconds; the agent then ends the
Runway session and leaves, and the game joins a fresh room for a new session. The agent also
leaves as soon as the player does.

Per reply the agent logs, in ms after it started on the batch: first token from Claude, first
audio from ElevenLabs, and first audible audio on the avatar's track.

## Deploy

The agent runs on LiveKit Cloud in region `us-east`, built from the `Dockerfile`. `livekit.toml`
holds the project and agent ID. Run these from the repo root; the `lk` CLI reads `LIVEKIT_URL`,
`LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` from the environment.

Redeploy after a code change:

```bash
lk agent deploy
```

Check that it is running, and read its logs:

```bash
lk agent status
```

```bash
lk agent logs
```

If the agent has been deleted, create a new one; this rewrites `livekit.toml`:

```bash
lk agent create --region us-east --secrets-file <file with the three secrets below>
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

The agent has no dispatch name, so it joins every new room in the project, and each room with a
player in it starts a Runway session. Delete the agent (`lk agent delete`) when you are not using it.

## Run locally instead

Needs the six variables above in your shell and a network that allows WebRTC. Stop the cloud agent
first or both will compete for the same rooms.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python agent.py dev
```
