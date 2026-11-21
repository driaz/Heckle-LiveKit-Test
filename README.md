# Heckle v2 narrator agent

The narrator for [Heckle](https://github.com/driaz/Heckle), running as a LiveKit agent:

game event or player speech → Claude (Opus 5.5 by default) → ElevenLabs v4 Turbo → Runway Characters avatar (preset `cat-character`, the cat)

Player speech is transcribed by ElevenLabs Scribe v2 realtime, using the same ElevenLabs key.

This repo started as a latency rig that fired 20 scripted events. Those results are in
[RESULTS.md](RESULTS.md). The agent now takes real events from the game instead.

## How it works

The game joins a new LiveKit room on page load. LiveKit dispatches this agent to the room; it
starts the avatar straight away (about 6 seconds to the first video frame) and then waits for
events and for the player to speak.

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

### Player speech

The game publishes the player's mic. Scribe's server-side voice detection ends the player's turn
after 0.6 seconds of silence, and the transcript goes to Claude as a normal user message. Event
messages are prefixed with `[event]` so Claude can tell the two apart.

The player's voice wins over events, and nothing is answered late:

- If the player says three or more words while the narrator is still preparing an event reply
  (nothing audible yet), that reply is dropped and the narrator answers the player instead. The
  event stays in the chat history, so the answer can still refer to it. Shorter sounds, such as
  "Ah!" on dying, leave the event reply alone.
- Once the narrator is audible, the player cannot interrupt it, and mic audio is discarded until
  it finishes. That keeps the narrator's own voice, coming out of the player's speakers, from
  being transcribed and answered. What the player says over it is not answered afterwards.

### Not talking over itself

The agent says one thing at a time. It starts a reply to events only when it is not thinking or
speaking, the player is not mid-sentence, and the avatar's audio track has been quiet for
1 second. Events that arrive in the meantime wait in an inbox that keeps at most one event per
kind:

- a newer event replaces an older one of the same kind; deaths keep a count ("died 3 times in a row")
- any newer event cancels a waiting stall
- deaths and stalls that have waited more than 15 seconds are dropped; checkpoints and the finish
  are kept

Whatever is left becomes a single reply.

### Session length

Runway caps a session at 5 minutes. No reply starts after 270 seconds; the agent then ends the
Runway session and leaves, and the game joins a fresh room for a new session. The agent also
leaves as soon as the player does.

Per reply the agent logs the line Claude wrote with its word count, first token from Claude, first
audio from ElevenLabs, and first audible audio on the avatar's track. For an event reply the times are in ms after it started on the
batch; for a speech reply, after the final transcript arrived.

## Narrator model

`agent.py` reads `HECKLE_LLM_MODEL` and falls back to `claude-opus-5-5` when it is unset or empty.
On LiveKit Cloud it is an agent secret; setting it restarts the agent. The agent logs the model
when a player joins.

Switch to Haiku:

```bash
lk agent update-secrets --secrets "HECKLE_LLM_MODEL=claude-haiku-5-5"
```

Back to Opus:

```bash
lk agent update-secrets --secrets "HECKLE_LLM_MODEL=claude-opus-5-5"
```

Haiku runs long, so any model with "haiku" in its name gets two extras. Opus gets neither: its
prompt is unchanged and it has no cap.

- A length rule appended to the prompt: one sentence of at most 15 words for an event, at most two
  sentences and 25 words for a reply to the player.
- A hard cap of 60 output tokens, about 30 spoken words. A reply that reaches it stops there, and
  its log line says `CUT OFF by the token cap`.

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
lk agent create --region us-east --secrets-file <file with the three keys below>
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
| `HECKLE_LLM_MODEL` | optional; the Claude model, default `claude-opus-5-5` |

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
