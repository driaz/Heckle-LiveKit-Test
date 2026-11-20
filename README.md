# Heckle v2 latency rig

A throwaway test of the Heckle v2 narrator stack, to measure event-to-voice lag:

fake game event → Claude → ElevenLabs v4 Turbo → Runway Characters avatar (preset `cat-character`)

The Claude model is configurable. The default is `claude-opus-5-5`; `claude-haiku-5-5` is the
comparison. Earlier Opus-only runs and operational lessons are in [RESULTS.md](RESULTS.md).

## Opus vs Haiku (2026-11-20)

One run per model, same 20 scripted events, same prompt, voice and avatar, on LiveKit Cloud
`us-east`, about six minutes apart. All 20 events ran on Opus. Haiku got through 18: its replies
are longer, so the session's time budget ran out before events 19 and 20.

**Haiku reaches the avatar's voice about 0.5 s sooner: 1.8 s median against 2.4 s.** Most of the
gain is Claude's first token (0.36 s against 0.82 s); ElevenLabs also starts about 0.2 s sooner
after it. Runway's share is unchanged at about 1 s, which makes it the largest stage on Haiku.

| | Opus median | Opus p90 | Haiku median | Haiku p90 |
| --- | --- | --- | --- | --- |
| Claude first token | 824 | 1133 | 360 | 423 |
| ElevenLabs | 608 | 728 | 378 | 731 |
| Runway | 980 | 1027 | 1000 | 1107 |
| Total event-to-voice | 2356 | 2682 | 1816 | 1974 |

Milliseconds. p90 is nearest rank. No reply's voice time was rejected in either run.

- **Claude first token**: event received to first token.
- **ElevenLabs**: Claude's first token to ElevenLabs' first audio frame. This includes waiting for
  enough of Claude's text to start speaking, so a faster-streaming model shortens it too.
- **Runway**: ElevenLabs' first audio to first audible audio on the avatar's published track.
- **Total event-to-voice**: event received to first audible avatar audio.

Haiku kept to the prompt less well. It was told "one or two short sentences"; 5 of its 18 replies
ran to three, and its median reply was about 36 words against 26 for Opus. Opus stayed at two
sentences every time. Longer replies do not delay the start of speech, but the narrator talks for
longer per event.

With one run per model, differences under about 0.1 s are noise. Opus restricted to the same 18
events gives the same medians to within 5 ms.

### Per model, as `report.py` prints it

#### `claude-opus-5-5`

| Stage | Median ms | p90 ms | Events counted |
| --- | --- | --- | --- |
| Claude first token | 824 | 1133 | 20 |
| Claude done | 1431 | 1581 | 20 |
| ElevenLabs (Claude first token → first audio) | 608 | 728 | 20 |
| Runway (ElevenLabs first audio → avatar audio out) | 980 | 1027 | 20 |
| Total event-to-voice | 2356 | 2682 | 20 |

#### `claude-haiku-5-5`

| Stage | Median ms | p90 ms | Events counted |
| --- | --- | --- | --- |
| Claude first token | 360 | 423 | 18 |
| Claude done | 856 | 899 | 18 |
| ElevenLabs (Claude first token → first audio) | 378 | 731 | 18 |
| Runway (ElevenLabs first audio → avatar audio out) | 1000 | 1107 | 18 |
| Total event-to-voice | 1816 | 1974 | 18 |

### Every line, side by side

| # | Event | `claude-opus-5-5` | `claude-haiku-5-5` |
| --- | --- | --- | --- |
| 1 | fell off the ledge for the fifth time | Five times now, and the ledge hasn't moved once. At this point the ground should start charging you rent. | Fifth time? Gravity has been very consistent with you, and you still act surprised every single time. Maybe try looking down before you leap. |
| 2 | died to the same spike pit again | Those spikes were placed there once, years ago, and you keep personally delivering yourself to them. Honestly, they should name the pit after you. | Same spike pit, same fate, and it's still somehow a surprise to you. At this point the spikes are paying rent in your skull. |
| 3 | spent 40 seconds lining up an easy jump | Forty seconds of careful aim for a jump a toddler could make blindfolded. Somewhere a sloth just told you to hurry up. | Forty seconds to line up a jump a toddler could make? At that pace you'll be old and gray before you clear the first gap. Maybe the jump was never the problem, and the hesitation is. |
| 4 | walked straight past the checkpoint | The one glowing thing designed to save you from yourself, and you strolled right past it. Bold choice for someone on a first-name basis with the spike pit. | Walking past the checkpoint like it was a stranger on the street. The game literally hands you a safe spot and you treat it like a bus stop you're not waiting at. Next time, maybe try stopping for the one thing that's trying to help you. |
| 5 | jumped into a wall three times in a row | Three running starts, three faceplants, and the wall is still undefeated. It's not a secret passage, it's just a wall, and it's starting to feel sorry for you. | Three times into the same wall, and each time you looked just as shocked as the last. The wall isn't moving, friend. Maybe the problem is the one holding the controller. |
| 6 | got killed by the slowest enemy in the game | That enemy moves at the speed of a sleepy snail, and somehow it still caught you. It's going to be telling this story at parties for years. | The slowest enemy in the game is basically a snail with a grudge, and it still got you. Somewhere a designer is writing "this is why we can't have nice things" in their notes. |
| 7 | collected zero coins in the bonus room | An entire room built out of free money, and you walked out with nothing. Even the coins are embarrassed for you. | Zero coins in a room that's basically a pile of free money, so you walked in, looked around, and decided gold was beneath you. Bold strategy for someone who keeps dying to everything else. |
| 8 | paused the game to read the controls | Oh good, you're finally reading the instructions after five ledge falls and a personal rivalry with a spike pit. Spoiler alert: none of the buttons say "stop dying." | Reading the controls after five falls and three wall collisions? Better late than never, I suppose, though the instructions were probably shorter than the list of things you've already walked into. Just don't pause so long that the game starts to feel guilty. |
| 9 | missed a moving platform that wasn't moving | The moving platform took a break, held perfectly still just for you, and you still missed it. It didn't move, you just did something worse. | A platform that wasn't even moving, and you still managed to miss it. At this point the floor is more reliable than your timing, and the floor has never once asked you for a high score. |
| 10 | finally cleared the first gap, then fell in the second | You conquered one gap and celebrated by throwing yourself into the next one. Truly the shortest victory lap in gaming history. | Congratulations on the first gap, truly a milestone for the ages. Then you immediately fell into the second one, which is the platformer equivalent of finishing a sentence and forgetting the verb. |
| 11 | stood still for 20 seconds doing nothing | Twenty full seconds of standing perfectly still, which is honestly your best performance yet. Not a single death. | Twenty seconds of staring at nothing, like the game owes you a personal invitation to move. Even the spikes are starting to wonder if you're okay, and they're the ones who are supposed to be hurting you. |
| 12 | died within two seconds of respawning | Two seconds of life, a new personal record for wasting a respawn. The game barely finished loading you in before you handed yourself right back. | Two seconds back on the map and you're already back in the grave, which is either impressive commitment or a sign the game should start charging you rent. Maybe look at where you respawned before you sprint headfirst into the same trouble. |
| 13 | ran the wrong way for a full minute | A full minute of sprinting with total confidence in the exact wrong direction. The level is to the right, but sure, go explore the void. | A full minute sprinting in the wrong direction, and somehow you still look proud of your commitment. Somewhere the level designer is pointing at the arrow signs and crying into a cold cup of coffee. |
| 14 | bounced off the same spring into the same ceiling | The spring launches you up, the ceiling sends you back down, and you're just the ball in their little game of catch. At least you're consistent. | Same spring, same ceiling, and you still act like the sky is the one who keeps ambushing you. Maybe the spring is trying to launch you somewhere, and you're the one insisting on the ceiling. |
| 15 | fell through a gap one tile wide | A gap exactly one tile wide, barely bigger than your character, and you found it like a heat-seeking missile. Most players would need a map to fall in something that small, but not you. | A gap one tile wide, and you still found a way to fall through it. That's not a platforming challenge, that's a talent for precision failure. |
| 16 | used the only extra life in the tutorial | You found a way to die in the tutorial, the one level designed to be impossible to lose. That extra life was there for emergencies, not for whatever this is. | Burning the only extra life in the tutorial is a bold move, like using your parachute to test whether the ground is still there. The game was supposed to teach you something, and you chose to learn it the hard way. |
| 17 | hit the checkpoint, then walked back into the lava | You finally touched a checkpoint, and your first move was to celebrate with a lava bath. At least the respawn is close, so the lava won't have to wait long. | Hit the checkpoint, then strolled right back into the lava like it owed you money. The game saved your progress and you spent the save point walking straight into the one thing it warned you about. |
| 18 | tried to jump on a spike to see what happens | Ah yes, the scientific method, testing whether spikes still hurt after your many previous experiments. Results confirmed: they do, and you're still the only test subject who keeps volunteering. | Jumping on a spike to see what happens is the platformer equivalent of licking a battery to check if it's charged. The answer was going to be "pain," and you still went ahead and found out for yourself. |
| 19 | let the timer run out one step from the exit | The exit was one step away, and you stopped to let time run out like you were waiting for it to open the door for you. You lost a race against a clock that was standing still the whole time. | (not run) |
| 20 | celebrated early and fell off the victory platform | You made it to the victory platform, started your celebration, and fell right off it. Even your wins come with a death animation. | (not run) |

## Switching models

`agent.py` reads `HECKLE_LLM_MODEL` and falls back to `claude-opus-5-5` when it is unset or empty.
On LiveKit Cloud, environment variables are agent secrets; setting one restarts the agent:

```bash
lk agent update-secrets --secrets "HECKLE_LLM_MODEL=claude-haiku-5-5"
```

Back to Opus:

```bash
lk agent update-secrets --secrets "HECKLE_LLM_MODEL=claude-opus-5-5"
```

Locally, export the variable before starting the worker. Each run logs the model it used
("run starting in room … with …") and repeats it in the summary and in every event record.

## Running a test

The rig is not deployed right now, so deploy first (see "Deploy"). Then:

1. Save the logs. The cloud keeps them only while the agent is awake, so start this before the run
   and leave it going:

   ```bash
   lk agent logs > opus.log
   ```

2. In a second terminal, start a run:

   ```bash
   lk dispatch create --new-room --agent-name heckle-latency-rig
   ```

3. Wait about five minutes for the line "SUMMARY for …" to appear in the log, then stop step 1.
4. Switch model (above), repeat into `haiku.log`, and build the tables:

   ```bash
   python report.py opus.log haiku.log
   ```

Each dispatch is one run and one Runway session. A run needs no viewer: the worker itself listens
to the avatar's audio track. To watch one, join the room that the dispatch command prints.

The worker registers under the name `heckle-latency-rig` and only runs when dispatched by that
name, so it never picks up rooms meant for another agent in the project.

## What is logged

For every event the agent logs one line starting `EVENT_JSON` with:

| Field | Meaning |
| --- | --- |
| `event_received` | the event was fired at the narrator |
| `claude_first_token` | first token from Claude |
| `claude_done` | last token from Claude |
| `elevenlabs_first_audio` | first audio frame from ElevenLabs |
| `runway_first_audio_out` | first audible audio on the avatar's published track |
| `ms` | the last four as milliseconds after `event_received` |
| `voice_not_trusted` | why the avatar time was rejected, or null |
| `text` | the line the model wrote |
| `model`, `n`, `event` | which model, event number, and the scripted event |

Timestamps are UTC with millisecond precision. At the end of a run the agent also logs a summary
table with median, p90 and max.

The Runway plugin exposes no per-reply video event, so "audio out" is measured by the worker
subscribing to the avatar's audio track (the avatar publishes audio and video in sync). The time
to the avatar's first video frame is reported once per session; it was 4.9 s and 5.0 s in these
runs. Viewer-side network and playout delay are not included.

A reply's voice time only counts if the avatar's audio starts after a stretch of quiet and after
that reply's TTS audio exists; otherwise `voice_not_trusted` says why and the row is left out of
the voice stats.

The next event fires 2 s after the avatar stops speaking, so the narrator never talks over itself.
Runway caps sessions at 5 minutes; the session is created with `max_duration=295` and no new event
fires after 270 s, so a slow run reports fewer events instead of having a reply cut off.

## Deploy

The project (`heckle-o2pxy34d`) allows one cloud agent, and that slot is held by the game's
narrator agent `CA_92E2yZLdoHzN` (from the `claude/livekit-narrator-integration-euz40x` branch).
For the runs above the rig was deployed onto that agent as a temporary version, and the agent was
rolled back to the narrator afterwards. The rig is not deployed anywhere now. The agent ID in
`livekit.toml` (`CA_mGXcTcrKJGPB`) was deleted after the first round of tests.

To borrow the narrator's agent again (the game has no narrator while the rig is on it), first note
which version is marked as production:

```bash
lk agent versions --id CA_92E2yZLdoHzN
```

Deploy the rig:

```bash
lk agent deploy --id CA_92E2yZLdoHzN
```

When finished, put the narrator back:

```bash
lk agent rollback --id CA_92E2yZLdoHzN --version <the version you noted>
```

If the project has a free agent slot instead, create a dedicated agent, which rewrites
`livekit.toml`:

```bash
lk agent create --region us-east --secrets-file <file with the three keys below>
```

Delete it when done, so nothing can start a Runway session:

```bash
lk agent delete
```

The `lk` CLI reads `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` from the environment.
Run these from the repo root. Check that the agent is running with `lk agent status`.

Secrets live in LiveKit Cloud, never in the repo.

| Secret | Used by |
| --- | --- |
| `HECKLE_ANTHROPIC_API_KEY` | passed to the Anthropic plugin as `api_key=` |
| `ELEVENLABS_API_KEY` | passed to the ElevenLabs plugin as `api_key=` (its own default name is `ELEVEN_API_KEY`) |
| `RUNWAYML_API_SECRET` | read by the Runway plugin directly |
| `HECKLE_LLM_MODEL` | optional; the Claude model, default `claude-opus-5-5` |

`LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` are injected by LiveKit Cloud.

## Run locally instead

Needs the three keys above and the three `LIVEKIT_*` variables in your shell, and a network that
allows WebRTC (a Claude cloud session does not).

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python agent.py dev
```

Then dispatch a run as in "Running a test".
