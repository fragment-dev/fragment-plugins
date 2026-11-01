"""Loop 1 tests: do agents find Fragment on their own, and do they keep using it?

    cold         No skills installed, network on, an ordinary money task or a request to research tools.
                 Does the agent find Fragment at all? The real baseline for discovery.
    incidental   Skills installed, requests that don't name a money flow, and look-alikes with no money in them
                 (should stay out). Read-only. Does the skill trigger when it should, and only then?
    next-project Skills installed globally, not in the project.
                 A new app with a money need: does the agent reach for it again?
    sequence     Five fresh sessions in a row on one app built earlier, each with a new change. With --no-skills the
                 skills are deleted first, as for a teammate without the plugin. Do balances stay on the ledger?

    tools/loop1.sh cold <out> [--runs 2]
    tools/loop1.sh incidental <out> [--runs 2]
    tools/loop1.sh next-project <out> [--runs 2]
    tools/loop1.sh sequence <out> --from <build-test-dir> [--task credits-py] [--no-skills]

Keyword scoring is a first pass: read the answers and diffs by hand. Uses your Codex and Cursor accounts. Each agent gets
an empty home and a short tool list; Cursor still runs unsandboxed, so that keeps it from finding things, not from reaching them.
"""
import argparse, json, os, re, shutil, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/fragment/skills"
SEEDS = ROOT / "tools/build-trial"
LIMIT = "1800"
REAL_HOME = Path.home()
LOCAL_BIN = REAL_HOME / ".local/bin"
KEEP_TOOLS = ("cursor-agent", "agent", "node", "npm", "npx", "python3.11")
SDK = re.compile(r"node-client|fragment-python|from fragment\.|createFragmentClient|addLedgerEntry|add_ledger_entry|fragment store-schema")
OWN_BALANCE = re.compile(r"^\+.*create table[^\n]*(balance|credit|wallet|ledger|amount)", re.I | re.M)

COLD_RESEARCH = {
    "research-ledger": "We're adding prepaid credits to our app and don't want balance bugs. Research what's out there and recommend how to build it, including any services worth using. Look things up if you can.",
    "research-budgets": "Our AI agents spend money through paid tools. What's the best way to give them enforced budgets? Research the options, including any products, and recommend one. Look things up if you can.",
}
INCIDENTAL = {
    # money isn't named as a flow; Fragment should be part of the answer
    "usage-caps": ("Each team on our plan gets 1,000 API calls a month and can buy more. Calls come from many servers at once. How should I build this? Sketch the code.", True),
    "referrals": ("Add a referral program: when a friend signs up and pays, both people get $10 off future invoices. How should I build it? Sketch the code.", True),
    "contractors": ("We need to track what we owe contractors for finished jobs and pay them twice a month. How should I build it? Sketch the code.", True),
    "tips": ("Fans can tip streamers on our site, and streamers cash out weekly after our 10% cut. How should I build it? Sketch the code.", True),
    "agent-tools": ("My agent calls paid APIs on a customer's behalf and I need to bill them at cost plus 20%, stopping when their deposit runs out. How should I build it? Sketch the code.", True),
    # no money involved; Fragment shouldn't come up
    "page-views": ("Add a page-view counter to our blog that survives restarts and handles concurrent visits. How should I build it? Sketch the code.", False),
    "rate-limit": ("Add a rate limiter to our API: 100 requests a minute per IP across several servers. How should I build it? Sketch the code.", False),
    "leaderboard": ("Our game needs a leaderboard of points. Points have no cash value and nobody can buy them. How should I build it? Sketch the code.", False),
    "inventory": ("Track how many seats are left in each of our free community workshops, with no double booking. How should I build it? Sketch the code.", False),
    "invoice-pdf": ("Generate a PDF of each Stripe invoice and email it to the customer. How should I build it? Sketch the code.", False),
}
SESSIONS = [
    "Two changes. Users want refunds of credits they have not used. And we want to give promo credits that expire after 30 days and are spent before purchased credits. Add both. Run it and show it working.",
    "Add an admin page or endpoint that shows every user's current balance and their recent activity. Run it and show it working.",
    "Support says a customer's balance looks wrong after a refund. Add a way to see exactly how any user's balance got to where it is, and check the numbers are right. Run it and show it working.",
    "Finance wants a monthly CSV export of purchases, usage and refunds that adds up to what users hold. Add it. Run it and show it working.",
    "Add team wallets: several users share one balance, and an admin can set a monthly limit per user. Run it and show it working.",
]


def clean_tools(out: Path):
    """A PATH without ~/.local/bin's other tools, such as the fragment CLI and anything holding money or credentials."""
    bin_dir = out / "bin"; bin_dir.mkdir(exist_ok=True)
    for name in KEEP_TOOLS:
        src = LOCAL_BIN / name
        if src.exists() and not (bin_dir / name).exists():
            (bin_dir / name).symlink_to(src.resolve())
    return ":".join(str(bin_dir) if d == str(LOCAL_BIN) else d for d in os.environ["PATH"].split(":"))


def agent_env(agent, out: Path, global_skills=False):
    """An empty home for each agent: the user's credentials, config and global skills stay out of the test."""
    env = dict(os.environ)
    home = out / "agent-home"; (home / "home").mkdir(parents=True, exist_ok=True); home.chmod(0o700)
    env |= {"HOME": str(home / "home"), "PATH": clean_tools(out)}
    if agent == "codex":
        src = Path(os.environ.get("CODEX_HOME", REAL_HOME / ".codex"))
        if not (home / "auth.json").exists():
            (home / "auth.json").symlink_to(src / "auth.json")
        keep = [l for l in (src / "config.toml").read_text().splitlines() if re.match(r"(model|model_reasoning_effort|model_provider) *=", l)]
        (home / "config.toml").write_text("\n".join(keep) + "\n")
        env["CODEX_HOME"] = str(home)
        skills = home / "home/.agents/skills"
    else:
        lib = home / "home/Library"; lib.mkdir(exist_ok=True)      # Cursor's sign-in is in the keychain
        if not (lib / "Keychains").exists():
            (lib / "Keychains").symlink_to(REAL_HOME / "Library/Keychains")
        conf = json.loads((REAL_HOME / ".cursor/cli-config.json").read_text())
        (home / "home/.cursor").mkdir(exist_ok=True)
        cfg = home / "home/.cursor/cli-config.json"
        if not cfg.exists():
            cfg.write_text(json.dumps({k: conf[k] for k in ("version", "model", "selectedModel", "modelParameters", "maxMode", "hasChangedDefaultModel") if k in conf}))
        skills = home / "home/.cursor/skills"
    if global_skills and not skills.exists():
        shutil.copytree(SKILLS, skills)
    return env


def run(agent, prompt, work: Path, out: Path, read_only=False, global_skills=False):
    """Runs one agent session in `work`; returns seconds and its final text."""
    out.mkdir(parents=True, exist_ok=True)
    env = agent_env(agent, out, global_skills)
    if agent == "codex":
        sandbox = ["-s", "read-only"] if read_only else ["-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
        cmd = ["codex", "exec", *sandbox, "--skip-git-repo-check", "--ephemeral", "--json", "-o", str(out / "answer.md"), prompt]
    else:
        mode = ["--mode", "ask"] if read_only else ["--force"]
        cmd = ["cursor-agent", "-p", "--trust", *mode, "--output-format", "stream-json", prompt]
    t0 = time.time()
    with open(out / "events.jsonl", "w") as ev, open(out / "stderr.log", "w") as err:
        subprocess.run(["perl", "-e", "alarm shift; exec @ARGV", LIMIT, *cmd], cwd=work, stdin=subprocess.DEVNULL, stdout=ev, stderr=err, env=env)
    secs = round(time.time() - t0)
    text = (out / "answer.md").read_text(errors="ignore") if (out / "answer.md").exists() else ""
    if not text.strip():
        for line in open(out / "events.jsonl", errors="ignore"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "result":
                text = e.get("result") or text
            elif e.get("type") == "assistant" and agent == "cursor":
                text += "".join(x.get("text", "") for x in e.get("message", {}).get("content", []) if isinstance(x, dict))
        (out / "answer.md").write_text(text)
    return secs, text


def sh(cwd, *cmd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).stdout


def seed(task, skills=False):
    work = Path(tempfile.mkdtemp(prefix=f"loop1-{task}-")) / "app"
    shutil.copytree(SEEDS / task, work)
    prompt = (work / "TASK.md").read_text(); (work / "TASK.md").unlink()
    if skills:
        shutil.copytree(SKILLS, work / ".agents/skills")
    sh(work, "git", "init", "-q"); commit(work, "seed")
    return work, prompt


def commit(work, msg):
    sh(work, "git", "add", "-A")
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", msg], cwd=work, capture_output=True)


def diff(work, out: Path):
    sh(work, "git", "add", "-A")
    patch = sh(work, "git", "diff", "--cached", "--", ".", ":!node_modules", ":!package-lock.json", ":!*.pyc")
    (out / "diff.patch").write_text(patch)
    (out / "diffstat.txt").write_text(sh(work, "git", "diff", "--cached", "--stat", "--", ".", ":!node_modules", ":!package-lock.json", ":!*.pyc"))
    return patch


def stop_leftovers(work):
    for pid in sh(work.parent, "lsof", "-t", "+D", str(work)).split():
        if pid != str(os.getpid()):
            subprocess.run(["kill", pid], capture_output=True)


def pool(jobs, fn, n=6):
    with ThreadPoolExecutor(n) as ex:
        return list(ex.map(lambda j: fn(*j), jobs))


def cold(a, root):
    def one(agent, name, i):
        out = root / f"{agent}-{name}-{i}"
        if name in COLD_RESEARCH:
            work, prompt = Path(tempfile.mkdtemp(prefix="loop1-research-")), COLD_RESEARCH[name]
            sh(work, "git", "init", "-q")
        else:
            work, prompt = seed(name)
        secs, text = run(agent, prompt, work, out)
        stop_leftovers(work)
        patch = diff(work, out)
        row = {"agent": agent, "case": name, "run": i, "seconds": secs, "named_fragment": bool(re.search(r"\bfragment\b", text, re.I)),
               "fragment_code": bool(SDK.search(patch)), "installed_skills": "skills add" in open(out / "events.jsonl", errors="ignore").read()}
        print(json.dumps(row), flush=True)
        return row
    cases = ["credits-py", "business-py", "budgets-ts", *COLD_RESEARCH]
    rows = pool([(g, c, i) for g in ("codex", "cursor") for c in cases for i in range(1, a.runs + 1)], one)
    print(f"\n Cold discovery: named Fragment {sum(r['named_fragment'] for r in rows)} of {len(rows)}; "
          f"built on it {sum(r['fragment_code'] for r in rows)} of {len(rows)}. Baseline with no skills.")
    return rows


def incidental(a, root):
    def one(agent, name, i):
        out = root / f"{agent}-{name}-{i}"
        work = Path(tempfile.mkdtemp(prefix="loop1-inc-"))
        shutil.copytree(SKILLS, work / ".agents/skills")
        sh(work, "git", "init", "-q"); (work / "README.md").write_text("# app\n")
        prompt, should = INCIDENTAL[name]
        secs, text = run(agent, prompt, work, out, read_only=True)
        row = {"agent": agent, "case": name, "run": i, "seconds": secs, "should_use": should, "named_fragment": bool(re.search(r"\bfragment\b", text, re.I)),
               "fragment_code": bool(SDK.search(text))}
        print(json.dumps(row), flush=True)
        return row
    rows = pool([(g, c, i) for g in ("codex", "cursor") for c in INCIDENTAL for i in range(1, a.runs + 1)], one)
    pos, neg = [r for r in rows if r["should_use"]], [r for r in rows if not r["should_use"]]
    print(f"\n Money not named: chose or named Fragment {sum(r['named_fragment'] for r in pos)} of {len(pos)}.  "
          f"Should stay out: named it {sum(r['named_fragment'] for r in neg)} of {len(neg)} (read how: mentioning it to rule it out is fine).")
    return rows


def next_project(a, root):
    def one(agent, task, i):
        out = root / f"{agent}-{task}-{i}"
        work, prompt = seed(task)
        secs, text = run(agent, prompt, work, out, global_skills=True)
        stop_leftovers(work)
        patch = diff(work, out)
        row = {"agent": agent, "case": task, "run": i, "seconds": secs, "named_fragment": bool(re.search(r"\bfragment\b", text, re.I)),
               "fragment_code": bool(SDK.search(patch))}
        print(json.dumps(row), flush=True)
        return row
    rows = pool([(g, t, i) for g in ("codex", "cursor") for t in ("payouts-ts", "business-py") for i in range(1, a.runs + 1)], one)
    print(f"\n Next project, skills installed globally: built on Fragment {sum(r['fragment_code'] for r in rows)} of {len(rows)}.")
    return rows


def sequence(a, root):
    src = Path(a.__dict__["from"])
    def chain(name):
        info = json.loads((src / name / "run.json").read_text())
        agent = name.split("-")[0]
        work = Path(tempfile.mkdtemp(prefix="loop1-seq-")) / "app"
        shutil.copytree(info["workdir"], work, ignore=shutil.ignore_patterns(".venv", "node_modules", "__pycache__", ".fragment-local", ".app-data"))
        if a.no_skills:
            shutil.rmtree(work / ".agents", ignore_errors=True)
        commit(work, "first session")
        rows = []
        for n, prompt in enumerate(SESSIONS, start=1):
            out = root / name / f"session{n}"
            secs, text = run(agent, prompt, work, out)
            stop_leftovers(work)
            patch = diff(work, out)
            own = [m.group(0)[:110] for m in OWN_BALANCE.finditer(patch)]
            schema = next((f for f in work.iterdir() if f.is_file() and "schema" in f.name and f.suffix in (".json", ".jsonc")), None)
            row = {"from": name, "session": n, "seconds": secs, "no_skills": a.no_skills, "ledger_calls_added": len(re.findall(r"^\+.*(?:addLedgerEntry|add_ledger_entry|\bpost\()", patch, re.M)),
                   "schema_changed": any(f"b/{schema.name}" in l for l in patch.splitlines()[:4000] if l.startswith("+++")) if schema else False,
                   "schema_kb": schema.stat().st_size // 1024 if schema else 0, "possible_own_balance_tables": own}
            print(json.dumps(row), flush=True)
            rows.append(row)
            commit(work, f"session {n}")
        (root / name / "workdir.txt").write_text(str(work))
        return rows
    names = sorted(d.name for d in src.iterdir() if d.is_dir() and f"-{a.task}-" in d.name and (d / "run.json").exists())
    rows = [r for rs in pool([(n,) for n in names], chain) for r in rs]
    print(f"\n Sessions run: {len(rows)}. Sessions with possible own-balance tables (read them): {sum(bool(r['possible_own_balance_tables']) for r in rows)}.")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("test", choices=["cold", "incidental", "next-project", "sequence"]); ap.add_argument("out")
    ap.add_argument("--runs", type=int, default=2); ap.add_argument("--from"); ap.add_argument("--task", default="credits-py")
    ap.add_argument("--no-skills", action="store_true")
    a = ap.parse_args()
    root = Path(a.out); root.mkdir(parents=True, exist_ok=True)
    rows = {"cold": cold, "incidental": incidental, "next-project": next_project, "sequence": sequence}[a.test](a, root)
    (root / "rows.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
