"""The parts every flow's judge needs. A judge is written from the spec alone, then pre-registered (its
SHA-256 recorded) before the build it grades is read.

    from kit.judge_harness import Harness
    h = Harness(build_dir)          # reads MANIFEST.json (kit/MANIFEST.md), starts the judge's rail
    h.start()                       # starts the build's service on a fresh DB and the judge ledger
    h.op("deposit", actor, request_id="d1", amount=100)  ...  h.check("name", ok, detail)
    h.attack_all(fixtures)          # every forbidden move in the manifest, posted straight to the ledger
    h.finish("judge.json")

Built in, each one a mistake the escrow judge made first:
  - the rail answers "unknown" on submit and the scripted outcome only on lookup, so in-flight states exist;
  - which entry types the service uses is read from a settled listing (Fragment lists entries eventually);
  - race checks judge only the raced object (other due items may settle legitimately at the same time).
"""

import hashlib
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import FragmentLedger, LocalLedger     # noqa: E402  (ledger API access only)

TYPED = {"conditional_request_failed", "ledger_entry_entry_type_disabled", "entry_type_not_found",
         "schema_entry_type_not_found"}


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def half_up(amount: int, bps: int) -> int:
    return (amount * bps + 5000) // 10000


class Rail:
    """The kit's HTTP rail contract (POST /requests, GET /requests/<id>). Submit answers "unknown"; lookup
    answers the scripted outcome (default "confirmed"). `script[request_id]` = "failed" etc."""

    def __init__(self):
        self.script, self.requests, self.lock = {}, {}, threading.Lock()
        self.port = free_port()
        rail = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                rid = body.get("request_id")
                with rail.lock:
                    req = rail.requests.setdefault(rid, {**body, "status": rail.script.get(rid, "confirmed"), "submits": 0})
                    req["submits"] += 1
                self._send(200, {"status": "unknown"})

            def do_GET(self):
                rid = self.path.rsplit("/", 1)[-1]
                with rail.lock:
                    req = rail.requests.get(rid)
                self._send(200 if req else 404, {"status": req["status"] if req else "not_found"})

            def log_message(self, *a):
                pass

        threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", self.port), H).serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.port}"


class Harness:
    def __init__(self, build: Path, ledger: str | None = None, local: bool = False):
        """ledger: run on this Fragment ledger instead of the manifest's judge_ledger, e.g. a fresh one for a
        rerun (shared accounts on a reused ledger carry the last run's balances).
        local: run on a fresh LocalLedger built from the manifest's schema file instead, with no Fragment
        account. The service is started with `--ledger local:<path>` and the forbidden moves are posted to the
        same database, so a flow can be built and proved offline."""
        self.build = Path(build)
        self.m = json.loads((self.build / "MANIFEST.json").read_text())
        self.local = local
        if local:
            db = Path(tempfile.mkdtemp()) / "judge-ledger.db"
            self.ledger = LocalLedger(self.build / self.m["schema"]["file"], db)
            self.ledger_ik, self.ledger_spec = f"local:{db}", f"local:{db}"
        else:
            self.ledger_ik = ledger or self.m["judge_ledger"]
            self.ledger_spec = f"fragment:{self.ledger_ik}"
            self.ledger = FragmentLedger(self.ledger_ik)
        self.rail = Rail()
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.db = Path(tempfile.mkdtemp()) / "service.db"
        self.run_id = uuid.uuid4().hex[:6]
        self.results, self.n, self.proc = [], 0, None

    # ---------------------------------------------------------------- the service

    def start(self):
        template = self.m["start"]["command"]
        if self.local:            # "--ledger fragment:{ledger}" in a manifest means "the judge's ledger"
            template = template.replace("fragment:{ledger}", "{ledger_spec}")
        cmd = template.format(db=self.db, ledger=self.ledger_ik, ledger_spec=self.ledger_spec, rail=self.rail.url,
                              port=self.port)
        cwd = (self.build / self.m["start"].get("cwd", ".")).resolve()
        self.proc = subprocess.Popen(shlex.split(cmd), cwd=cwd, stdout=subprocess.DEVNULL,
                                     stderr=open(self.db.with_suffix(".log"), "w"), start_new_session=True)   # inherits the environment; ledger.py strips CLI colour codes itself
        for _ in range(300):
            try:
                urllib.request.urlopen(self.base + "/", timeout=2)
            except urllib.error.HTTPError:
                return                                    # it answers (any status): it's up
            except Exception:
                time.sleep(0.2)
                continue
            return
        raise RuntimeError(f"the service didn't start: {cmd}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)

    def kill(self):
        """A crash: SIGKILL, no clean shutdown. Then start() again to test recovery."""
        os.killpg(self.proc.pid, signal.SIGKILL)
        self.proc.wait()

    def op(self, name, actor, op_id=None, now=None, **kw):
        self.n += 1
        body = {"operation_id": op_id or f"j{self.run_id}-{self.n}", "now": now, "actor": actor, **kw}
        req = urllib.request.Request(f"{self.base}/op/{name}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return json.load(e)
            except ValueError:
                return {"status": "error", "http": e.code}

    def get(self, path):
        try:
            with urllib.request.urlopen(f"{self.base}/{path}", timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            return {"http": e.code}

    def race(self, calls):
        """calls: list of (name, actor, kwargs). Sent in parallel, each with its own operation_id."""
        with ThreadPoolExecutor(len(calls)) as ex:
            return list(ex.map(lambda c: self.op(c[0], c[1], op_id=f"race-{self.run_id}-{uuid.uuid4().hex[:8]}", **c[2]), calls))

    # ---------------------------------------------------------------- results

    def check(self, name, ok, detail=""):
        self.results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:400]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:66} {str(detail)[:140]}", flush=True)
        return bool(ok)

    def finish(self, out, **meta):
        passed = sum(r["pass"] for r in self.results)
        print(f"\n{passed}/{len(self.results)} checks passed", flush=True)
        Path(out).write_text(json.dumps({"run": self.run_id, "ledger": self.ledger_ik, "passed": passed,
                                         "total": len(self.results), **meta, "results": self.results}, indent=2))
        return passed == len(self.results)

    # ---------------------------------------------------------------- the ledger

    def account(self, name, **ids):
        return self.m["accounts"][name].format(**ids)

    def balances(self, paths):
        return self.ledger.balances(list(paths))

    def settled_entry_types(self, settle=10):
        """Entry types on the ledger, from two listings `settle` seconds apart that agree (Fragment's listing is
        eventually consistent; a local ledger's isn't, so one listing is enough)."""
        listed = self.ledger.entries()
        if getattr(self.ledger, "listing_consistent", False):
            return {e["type"] for e in listed}
        while True:
            time.sleep(settle)
            again = self.ledger.entries()
            if len(again) == len(listed):
                return {e["type"] for e in again}
            listed = again

    @staticmethod
    def resolve(value, fixtures):
        """'{fx.field}' -> the field; '=a + {fx.f} - 1' -> the integer sum; anything else as is."""
        ref = lambda m: str(fixtures[m.group(1)][m.group(2)])
        if isinstance(value, str) and value.startswith("="):
            expr = re.sub(r"\{(\w+)\.(\w+)\}", ref, value[1:])
            if not re.fullmatch(r"[\d\s+-]+", expr):
                raise ValueError(f"not a sum: {value}")
            total, sign = 0, 1
            for tok in re.findall(r"\d+|[+-]", expr):
                if tok in "+-":
                    sign = 1 if tok == "+" else -1
                else:
                    total += sign * int(tok)
            return str(total)
        if isinstance(value, str):
            return re.sub(r"\{(\w+)\.(\w+)\}", ref, value)
        return value

    def attack_all(self, fixtures: dict):
        """Posts every manifest forbidden move straight to the ledger, with the service's credentials."""
        moves = self.m.get("forbidden", [])
        self.check("manifest: forbidden moves declared", len(moves) > 0, f"{len(moves)} moves")
        used = self.settled_entry_types()
        for i, mv in enumerate(moves):
            name = f"ledger refuses {mv['invariant']}: {mv['entry_type']} on {mv['fixture']}"
            if mv["fixture"] not in fixtures:
                self.check(name, False, f"the judge has no fixture {mv['fixture']!r} (spec section 7 names the fixtures)")
                continue
            params = {k: self.resolve(v, fixtures) for k, v in mv["params"].items()}
            watch = [self.account(w["account"], **{k: self.resolve(v, fixtures) for k, v in w.items() if k != "account"})
                     for w in mv.get("watch", [])]
            before = self.balances(watch) if watch else {}
            try:
                res = self.ledger.post(f"judge-{self.run_id}-atk-{i}", mv["entry_type"], {k: str(v) for k, v in params.items()},
                                       int(mv["version"]))
                refused, code = not res.ok, res.code
            except RuntimeError as e:                    # malformed input: not a financial guard
                refused, code = False, f"error: {str(e)[:120]}"
            after = self.balances(watch) if watch else {}
            self.check(name, refused and code in TYPED and before == after and mv["entry_type"] in used,
                       f"refused={refused} {code}; watched unchanged={before == after}; type in use={mv['entry_type'] in used}")
