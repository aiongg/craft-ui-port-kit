"""track eta: cycles left times the median cycle, sets left over the measured rate, the weekly quota at the finish."""
import json

from lib import check


def cycle_event(t, label, batch, total, gap, code, pct):
    return {"t": t, "id": label, "kind": "cycle", "ok": code == 0, "text": f"cycle ok: {label}",
            "data": {"label": label, "batch": batch, "total_s": total, "gap_s": gap, "exit": code, "weekly_pct": pct}}


def write(s, events):
    d = s.work / "track"
    d.mkdir(exist_ok=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def case_cycle_model(s):
    s.config({"plan.build_batches": 3})
    ev = [
        # batch b1: three cycles of 10 min plus 5 min between them, green at the third
        cycle_event("2026-01-01T00:00:00Z", "b1-1", "b1", 600, None, 1, 10),
        cycle_event("2026-01-01T00:15:00Z", "b1-2", "b1", 600, 300, 1, 12),
        cycle_event("2026-01-01T00:30:00Z", "b1-3", "b1", 600, 300, 0, 14),
        # batch b2: its first cycle, after a gap across the batch change that is no cycle period
        cycle_event("2026-01-01T02:00:00Z", "b2-1", "b2", 600, 4800, 1, 20),
    ]
    write(s, ev)
    p = s.run("track", "eta", "--json")
    check(p.returncode == 0, "track eta runs", p)
    c = json.loads(p.stdout)
    check(c["period_s"] == 900 and c["periods_measured"] == 2, f"median period from in-batch cycles: {c}")
    check(c["per_batch"] == 3 and c["batches_seen"] == 2, f"cycles per finished batch: {c}")
    check(c["left"] == 2 + 3, f"two left in b2, three for the batch still to come: {c['left']}")
    check(c["cycle_h"] == 1.2 and c["total_h"] == 1.2, f"5 cycles of 15 min: {c}")
    w = c["weekly"]
    check(w["now_pct"] == 20 and w["per_h"] == 5.0 and w["at_finish_pct"] == 26.2 and not w["passes"], f"weekly: {w}")
    p = s.run("track", "eta")
    check("cycles left: 5 = 1.2 h" in p.stdout and "weekly quota: 20 % used" in p.stdout, "text view", p)


def case_unset_batches_and_reset(s):
    write(s, [cycle_event("2026-01-01T00:00:00Z", "a-1", "a", 600, None, 1, 90),
              cycle_event("2026-01-01T01:00:00Z", "a-2", "a", 600, 3000, 1, 5)])
    c = json.loads(s.run("track", "eta", "--json").stdout)
    check(c["left"] is None and any("plan.build_batches unset" in n for n in c["notes"]), f"says what it counts: {c}")
    check(c["weekly"]["now_pct"] == 5 and c["weekly"]["per_h"] is None, f"a reset starts the samples again: {c['weekly']}")
