"""Turn agent logs into the comparison tables: python report.py opus.log haiku.log sonnet.log

Each file is the saved output of `lk agent logs` for one run. Prints Markdown.
"""

import json
import math
import statistics
import sys

PREFIX = "EVENT_JSON "
# stage name -> (start stamp, end stamp); None = the event itself
STAGES = {
    "Claude first token": (None, "llm"),
    "Claude done": (None, "llm_done"),
    "ElevenLabs (Claude first token → first audio)": ("llm", "tts"),
    "Runway (ElevenLabs first audio → avatar audio out)": ("tts", "voice"),
    "Total event-to-voice": (None, "voice"),
}


def load(path: str) -> list[dict]:
    """The per-event records in a log file, last one wins if an event number repeats."""
    records: dict[int, dict] = {}
    decoder = json.JSONDecoder()
    for line in open(path, encoding="utf-8", errors="replace"):
        # the cloud log viewer JSON-escapes the message, so undo that before parsing
        for text in (line, line.replace('\\"', '"').replace("\\\\", "\\")):
            at = text.find(PREFIX)
            if at < 0:
                continue
            try:
                rec, _ = decoder.raw_decode(text[at + len(PREFIX) :])
            except ValueError:
                continue
            records[rec["n"]] = rec
            break
    return [records[n] for n in sorted(records)]


def stage_ms(rec: dict, stage: str) -> int | None:
    start, end = STAGES[stage]
    if "voice" in (start, end) and rec["voice_not_trusted"]:
        return None
    a = 0 if start is None else rec["ms"][start]
    b = rec["ms"][end]
    return None if a is None or b is None else b - a


def stats_table(recs: list[dict]) -> str:
    lines = ["| Stage | Median ms | p90 ms | Events counted |", "| --- | --- | --- | --- |"]
    for stage in STAGES:
        v = sorted(x for r in recs if (x := stage_ms(r, stage)) is not None)
        if v:
            p90 = v[math.ceil(0.9 * len(v)) - 1]  # nearest rank
            lines.append(f"| {stage} | {statistics.median(v):.0f} | {p90} | {len(v)} |")
        else:
            lines.append(f"| {stage} | - | - | 0 |")
    return "\n".join(lines)


def main(paths: list[str]) -> None:
    runs = [load(p) for p in paths]
    names = [recs[0]["model"] if recs else p for recs, p in zip(runs, paths)]
    for name, recs in zip(names, runs):
        print(f"### `{name}`\n\n{stats_table(recs)}\n")

    print("### Lines\n")
    print("| # | Event | " + " | ".join(f"`{n}`" for n in names) + " |")
    print("| --- | --- |" + " --- |" * len(names))
    by_n = [{r["n"]: r for r in recs} for recs in runs]
    for n in sorted(set().union(*by_n)):
        event = next(run[n]["event"] for run in by_n if n in run)
        cells = [run[n]["text"].replace("|", "\\|") if n in run else "(not run)" for run in by_n]
        print(f"| {n} | {event} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
