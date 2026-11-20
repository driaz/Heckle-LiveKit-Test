"""First-token probe: the rig's prompts sent straight to the Claude API, no ElevenLabs or Runway.

python probe.py out.jsonl claude-sonnet-5-5,claude-opus-5-5 <rounds> <seconds between rounds> 20 <mode>

mode: forward (the rig's order), reversed, or standalone (each event alone, no history).
Models are called one after another per event. Appends one JSON record per call to out.jsonl:
first_ms is the time to the first text token, done_ms to the last. Needs HECKLE_ANTHROPIC_API_KEY.
"""
import json, os, sys, time, datetime
import anthropic
from agent import EVENTS, INSTRUCTIONS

MODELS = sys.argv[2].split(",")
ROUNDS, GAP_BETWEEN_ROUNDS_S, N = int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
MODE = sys.argv[6]  # forward | reversed | standalone
ORDER = list(enumerate(EVENTS[:N], 1))
if MODE == "reversed":
    ORDER.reverse()
client = anthropic.Anthropic(api_key=os.environ["HECKLE_ANTHROPIC_API_KEY"], base_url="https://api.anthropic.com", max_retries=0)
out = open(sys.argv[1], "a")
for rnd in range(1, ROUNDS + 1):
    history = {m: [] for m in MODELS}  # each model builds its own conversation, as on the rig
    for pos, (n, event) in enumerate(ORDER, 1):
        for m in MODELS:
            history[m].append({"role": "user", "content": f"The player {event}."})
            rec = {"mode": MODE, "round": rnd, "pos": pos, "n": n, "model": m, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
            t0 = time.perf_counter(); text = ""
            try:
                with client.messages.stream(model=m, max_tokens=1024, system=INSTRUCTIONS, messages=history[m]) as stream:
                    for chunk in stream.text_stream:
                        if "first_ms" not in rec:
                            rec["first_ms"] = round((time.perf_counter() - t0) * 1000)
                        text += chunk
                rec["done_ms"] = round((time.perf_counter() - t0) * 1000)
            except Exception as e:
                rec["error"] = repr(e)[:200]
            history[m].append({"role": "assistant", "content": text or "..."})
            if MODE == "standalone":
                history[m] = []
            out.write(json.dumps(rec) + "\n"); out.flush()
        time.sleep(2)
    if rnd < ROUNDS:
        time.sleep(GAP_BETWEEN_ROUNDS_S)
