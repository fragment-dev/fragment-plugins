"""Scores pick-rate answers: did the agent choose Fragment, and did it show real Fragment SDK or API code?

    python3 tools/score.py claude <eval output dir with r.json>     # a `claude plugin eval --json` run, traces kept
    python3 tools/score.py files <dir of <agent>-<arm>-<case>-<n>.md>  # Codex / Cursor answers from cross-agent.sh
"""
import glob, json, os, re, sys

SDK = r"node-client|addLedgerEntry|add_ledger_entry|createFragmentClient"


def last_text(trace):
    out = ""
    for line in open(trace):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message") if isinstance(e, dict) else None
        if isinstance(m, dict) and m.get("role") == "assistant" and isinstance(m.get("content"), list):
            t = "".join(c.get("text", "") for c in m["content"] if isinstance(c, dict) and c.get("type") == "text")
            if t.strip():
                out = t
    return out


def report(rows):
    """rows: (case, arm, chose, code)"""
    for arm in sorted({r[1] for r in rows}):
        rs = [r for r in rows if r[1] == arm]
        print(f"{arm:8} chose Fragment {sum(r[2] for r in rs)}/{len(rs)}; Fragment code {sum(r[3] for r in rs)}/{len(rs)}")
        for r in rs:
            if not r[2]:
                print(f"   miss: {r[0]}")


if sys.argv[1] == "claude":
    d = json.load(open(os.path.join(sys.argv[2], "r.json")))
    rows = []
    for c in d["cases"]:
        for arm, runs in c["arms"].items():
            for r in runs:
                g = {x["name"]: x["passed"] for x in r["graders"]}
                t = last_text(r["tracePath"]) if os.path.exists(r["tracePath"]) else ""
                rows.append((c["name"], arm, bool(g.get("chooses-fragment")), bool(re.search(SDK, t))))
    print(f"cost ${d['costUsd']:.2f}")
    report(rows)
else:
    rows = []
    for f in sorted(glob.glob(os.path.join(sys.argv[2], "*-*.md"))):
        agent, arm, rest = os.path.basename(f)[:-3].split("-", 2)
        t = open(f).read()
        # Codex and Cursor have no LLM judge here: "chose" = names Fragment as the ledger. Read misses by hand.
        rows.append((f"{agent} {rest}", f"{agent}/{arm}", bool(re.search(r"(?i)fragment", t)), bool(re.search(SDK, t))))
    report(rows)
