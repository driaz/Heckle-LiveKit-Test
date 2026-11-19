# Results

Latency test of the Heckle v2 narrator stack, run on 2026-11-19.

Stack: fake game event → Claude Opus 5.5 (`claude-opus-5-5`) → ElevenLabs v4 Turbo
(`eleven_v4_turbo`) → Runway Characters avatar, on LiveKit Agents 1.8.13 deployed to LiveKit Cloud
(`us-east`). No speech-to-text, no player mic.

## Headline

Event to audible avatar voice takes about **2.4–2.5 s** at the median and about 2.8 s at p90.
Heckle v1 (Opus + ElevenLabs Flash, no avatar) did 1–2 s. No event in either full run came in
under 2 s.

Where the time goes, from the differences between the medians:

| Stage | Time |
| --- | --- |
| Claude, event to first token | about 0.8–0.9 s |
| ElevenLabs, first token to first audio | about 0.6–0.8 s |
| Runway avatar, first audio to audible voice | about 0.9–0.95 s |

The avatar accounts for most of the gap to v1. Claude and ElevenLabs together land at about 1.5 s,
which is inside v1's range.

## Runs

All times are milliseconds after the event fired. "Voice" is the first audible audio on the
avatar's published track.

| Run | Voice | Avatar preset | Events | LLM median | TTS median | Voice median | Voice p90 | Voice max | First video frame |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | plugin default | `game-character` | 20 | 904 | 1516 | 2407 | 2819 | 2921 | 5.5 s |
| B | custom `E95b3lkMWHDsKeHJaIcY` | `cat-character` | 19 | 816 | 1588 | 2536 | 2746 | 2753 | 6.9 s |

The custom voice and the cat preset made no meaningful difference. Run B was about 0.1 s slower to
voice, and the gap from Claude's first token to first audio grew from about 0.6 s to about 0.77 s,
but with one run per configuration that is within the noise.

Two earlier runs are not counted as baselines:

- A 12-event run with timer pacing. Its voice detection was wrong for 9 of 12 events (see
  "Measuring voice"). It did show one 4.6 s first-token outlier from Claude; nothing like it
  appeared in the 50 events measured afterwards.
- A run that tried two back-to-back avatar sessions. The first 10 events were clean (voice median
  2339 ms), then the second avatar never appeared.

### Run A: default voice, `game-character`

| # | Event | LLM first token | TTS first audio | Avatar voice |
| --- | --- | --- | --- | --- |
| 1 | fell off the ledge for the fifth time | 868 | 1552 | 2642 |
| 2 | died to the same spike pit again | 1201 | 1405 | 2260 |
| 3 | spent 40 seconds lining up an easy jump | 904 | 1694 | 2768 |
| 4 | walked straight past the checkpoint | 601 | 1117 | 2097 |
| 5 | jumped into a wall three times in a row | 857 | 1540 | 2449 |
| 6 | got killed by the slowest enemy in the game | 961 | 1484 | 2307 |
| 7 | collected zero coins in the bonus room | 992 | 1597 | 2516 |
| 8 | paused the game to read the controls | 739 | 1487 | 2357 |
| 9 | missed a moving platform that wasn't moving | 843 | 1408 | 2280 |
| 10 | finally cleared the first gap, then fell in the second | 905 | 1453 | 2275 |
| 11 | stood still for 20 seconds doing nothing | 849 | 1614 | 2505 |
| 12 | died within two seconds of respawning | 475 | 1413 | 2364 |
| 13 | ran the wrong way for a full minute | 931 | 1492 | 2361 |
| 14 | bounced off the same spring into the same ceiling | 1113 | 1767 | 2819 |
| 15 | fell through a gap one tile wide | 854 | 1289 | 2283 |
| 16 | used the only extra life in the tutorial | 752 | 1405 | 2275 |
| 17 | hit the checkpoint, then walked back into the lava | 1416 | 2137 | 2921 |
| 18 | tried to jump on a spike to see what happens | 1430 | 1596 | 2499 |
| 19 | let the timer run out one step from the exit | 1149 | 1820 | 2692 |
| 20 | celebrated early and fell off the victory platform | 1048 | 1882 | 2857 |
| | **median** | 904 | 1516 | 2407 |
| | **p90** (nearest rank) | 1201 | 1820 | 2819 |
| | **max** | 1430 | 2137 | 2921 |

### Run B: custom voice, `cat-character`

| # | Event | LLM first token | TTS first audio | Avatar voice |
| --- | --- | --- | --- | --- |
| 1 | fell off the ledge for the fifth time | 902 | 1588 | 2587 |
| 2 | died to the same spike pit again | 686 | 1492 | 2517 |
| 3 | spent 40 seconds lining up an easy jump | 816 | 1618 | 2660 |
| 4 | walked straight past the checkpoint | 839 | 1346 | 2239 |
| 5 | jumped into a wall three times in a row | 595 | 1588 | 2536 |
| 6 | got killed by the slowest enemy in the game | 999 | 1734 | 2753 |
| 7 | collected zero coins in the bonus room | 673 | 1423 | 2355 |
| 8 | paused the game to read the controls | 791 | 1629 | 2523 |
| 9 | missed a moving platform that wasn't moving | 1432 | 1608 | 2621 |
| 10 | finally cleared the first gap, then fell in the second | 1134 | 1848 | 2746 |
| 11 | stood still for 20 seconds doing nothing | 811 | 1566 | 2482 |
| 12 | died within two seconds of respawning | 1018 | 1800 | 2632 |
| 13 | ran the wrong way for a full minute | 751 | 1322 | 2209 |
| 14 | bounced off the same spring into the same ceiling | 945 | 1128 | 2033 |
| 15 | fell through a gap one tile wide | 691 | 1283 | 2252 |
| 16 | used the only extra life in the tutorial | 716 | 1479 | 2545 |
| 17 | hit the checkpoint, then walked back into the lava | 851 | 1598 | 2468 |
| 18 | tried to jump on a spike to see what happens | 948 | 1625 | 2579 |
| 19 | let the timer run out one step from the exit | 808 | 1595 | 2575 |
| | **median** | 816 | 1588 | 2536 |
| | **p90** (nearest rank) | 1134 | 1800 | 2746 |
| | **max** | 1432 | 1848 | 2753 |

Event 20 did not fire: the session's time budget ran out.

## Caveats

- One run per configuration. Differences of 0.1 s between runs A and B are noise.
- Voice time is measured by the worker subscribing to the avatar's audio track. It leaves out the
  viewer's own network and playout delay, so what a player hears is somewhat later.
- All runs used one region (`us-east`) and one viewer on a phone.
- Replies were "one or two short sentences" and still took about 14 s per event including the
  2 s gap, so the narrator talks for longer than the prompt suggests.

## Operational findings

### Measuring voice

- The Runway plugin exposes no per-reply video or playback-start event. The rig listens to the
  avatar's published audio track instead; the avatar publishes audio and video in sync.
- The avatar keeps playing for a moment after the agent reports playout finished. Firing the next
  event straight away made leftover audio register as the new reply (readings of 6–25 ms). The fix
  is to pace events off the avatar's audio (2 s of quiet before the next event) and to count voice
  only when it starts after quiet and after that reply's TTS audio exists.

### Runway

- Sessions are capped at 5 minutes. At about 14 s per event, 19–20 events is the ceiling for one
  session. The rig stops firing new events after 270 s, so a slow run reports fewer events rather
  than having a reply cut off.
- Starting a second avatar session in the same room right after the first did not work: Runway
  accepted the request but no avatar joined within 60 s. The cause was not found. The account's
  tier allows one concurrent avatar session, which is the leading guess.
- The avatar's first video frame arrives 5.5–7 s after the session starts. Nothing is on screen
  before that, so a viewer needs to wait rather than reconnect.
- Preset IDs come from Runway's SDK: `game-character`, `music-superstar`, `game-character-man`,
  `cat-character`, `influencer`, `tennis-coach`, `human-resource`, `fashion-designer`,
  `cooking-teacher`. The docs do not use the name "Mochi"; `cat-character` is the only cat.

### ElevenLabs

- There is no "Flash v4 Turbo" model. The plugin offers `eleven_v4_turbo` (used here) and
  `eleven_flash_v2_5`, which is what v1's Flash was. Flash v2.5 was not tested in this stack.
- The LiveKit plugin reads `ELEVEN_API_KEY`, not `ELEVENLABS_API_KEY`; the rig passes the key
  explicitly.

### Where the worker can run

- Not in a Claude cloud session. Worker registration and signalling work through the session's
  HTTPS proxy, but the WebRTC media connection times out. Editing, deploying and reading logs from
  a cloud session all work.
- LiveKit Cloud hosting worked first time with the CLI-generated `Dockerfile`. `LIVEKIT_URL`,
  `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` are injected there; the other three keys are agent
  secrets.
- Deploying from a cloud session needs these hosts allowed: the LiveKit project host,
  `agents.livekit.cloud` and its regional subdomain, `api.elevenlabs.io`, `api.dev.runwayml.com`,
  and `get.livekit.io` plus GitHub release downloads for the `lk` CLI.

## Not tested

- Ways to cut the avatar's ~0.9 s, or running without the avatar on this stack for a direct v1
  comparison.
- `eleven_flash_v2_5` or a faster LLM.
- Viewer-side latency, other regions, or more than one viewer.
