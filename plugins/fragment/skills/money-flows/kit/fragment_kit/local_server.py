"""A local Fragment endpoint: the real Fragment SDKs talk to it as they would to Fragment, with no account.

Each ledger is a LocalLedger (ledger.py): the same schema rules and conditions, stored in SQLite under --dir.
Point the SDK at it, and change only these settings to go live:

    python3 local_server.py --schema schema.jsonc --ledger app-credits      # http://127.0.0.1:8787

    apiUrl   http://127.0.0.1:8787/graphql
    authUrl  http://127.0.0.1:8787/oauth2/token
    clientId, clientSecret, scope: any non-empty value

It answers the ledger calls an app makes: addLedgerEntry, addLedgerEntries, ledgerAccount (balance),
ledger (with ledgerEntries and ledgerAccounts), ledgerEntry, storeSchema, createLedger and workspace. Anything
else (payments, links, reconciliation, reversals, migrations) answers with an error naming the operation:
run that against a Fragment workspace. It listens on 127.0.0.1 only and accepts any credentials, so it is for
development on one machine, never a deployment.
"""

import argparse
import json
import re
import secrets
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ledger import LocalLedger, load_schema

FIELD = re.compile(r"^\s*(?:(?:query|mutation)\b[^{]*)?\{\s*(?:\w+\s*:\s*)?(\w+)", re.S)
COMMENT = re.compile(r"#[^\n]*")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Ledgers:
    """Schemas and ledgers under one directory: schemas/<key>.json, ledgers.json, <ledger ik>.db."""

    def __init__(self, root: Path):
        self.root = root
        (root / "schemas").mkdir(parents=True, exist_ok=True)
        self.index_file = root / "ledgers.json"
        self.index = json.loads(self.index_file.read_text()) if self.index_file.exists() else {}
        self.open: dict[str, LocalLedger] = {}
        self.lock = threading.Lock()

    def store_schema(self, schema: dict) -> dict:
        key = schema.get("key")
        if not key:
            raise BadRequest("bad_request", "the schema needs a key")
        f = self.root / "schemas" / f"{key}.json"
        versions = json.loads(f.read_text())["versions"] if f.exists() else []
        if not versions or versions[-1]["json"] != schema:
            versions.append({"version": len(versions) + 1, "created": now(), "json": schema})
            f.write_text(json.dumps({"versions": versions}))
            with self.lock:     # ledgers on this schema pick up the new version
                for ik in [ik for ik, m in self.index.items() if m["schema"] == key]:
                    self.open.pop(ik, None)
        v = versions[-1]
        return {"key": key, "name": schema.get("name", key), "version": {"version": v["version"], "created": v["created"]}}

    def schema_file(self, key: str) -> Path:
        f = self.root / "schemas" / f"{key}.json"
        if not f.exists():
            raise BadRequest("not_found", f"no schema with key {key}; store it first")
        out = self.root / "schemas" / f"{key}.current.json"
        out.write_text(json.dumps(json.loads(f.read_text())["versions"][-1]["json"]))
        return out

    def create(self, ik: str, name: str, schema_key: str) -> tuple[dict, bool]:
        self.schema_file(schema_key)
        with self.lock:
            if ik in self.index:
                return self.view(ik), True
            self.index[ik] = {"id": f"ledger_{uuid.uuid4().hex[:12]}", "name": name or ik,
                              "schema": schema_key, "created": now()}
            self.index_file.write_text(json.dumps(self.index, indent=1))
        return self.view(ik), False

    def view(self, ik: str) -> dict:
        m = self.index[ik]
        return {"id": m["id"], "ik": ik, "name": m["name"], "created": m["created"], "balanceUTCOffset": "+00:00",
                "schema": {"key": m["schema"]}}

    def get(self, ik: str) -> LocalLedger:
        with self.lock:
            if ik not in self.index:
                raise BadRequest("not_found", f"no ledger with ik {ik}")
            if ik not in self.open:
                self.open[ik] = LocalLedger(self.schema_file(self.index[ik]["schema"]), self.root / f"{ik}.db")
            return self.open[ik]


class BadRequest(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message

    def result(self) -> dict:
        return {"__typename": "BadRequestError", "code": self.code, "message": self.message, "retryable": False}


class Api:
    def __init__(self, ledgers: Ledgers):
        self.ledgers = ledgers

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def arg(query: str, name: str):
        """An inline string argument (`name: "value"`), for clients that don't use variables."""
        m = re.search(name + r'\s*:\s*"([^"]*)"', query)
        return m.group(1) if m else None

    def entry_view(self, ledger_ik: str, ik: str) -> dict | None:
        led = self.ledgers.get(ledger_ik)
        with led.lock:
            row = led.db.execute("SELECT type, lines, seq FROM entries WHERE ik = ?", (ik,)).fetchone()
        if not row:
            return None
        lines = json.loads(row[1])
        created = self.created(ledger_ik, ik)
        return {"id": f"entry_{ledger_ik}_{row[2]}", "ik": ik, "type": row[0], "posted": created, "created": created,
                "description": "", "hidden": False,
                # as Fragment: an entry read back pages its lines; addLedgerEntry returns them as a list
                "lines": self.page([{"id": f"line_{row[2]}_{n}", "amount": str(a), "account": {"path": p}}
                                    for n, (p, a) in enumerate(lines.items())])}

    def created(self, ledger_ik: str, ik: str) -> str:
        led = self.ledgers.get(ledger_ik)
        with led.lock:
            led.db.execute("CREATE TABLE IF NOT EXISTS entry_times (ik TEXT PRIMARY KEY, created TEXT NOT NULL)")
            led.db.execute("INSERT OR IGNORE INTO entry_times VALUES (?, ?)", (ik, now()))
            return led.db.execute("SELECT created FROM entry_times WHERE ik = ?", (ik,)).fetchone()[0]

    def add_entry(self, ik: str, entry: dict) -> dict:
        ledger_ik = (entry.get("ledger") or {}).get("ik")
        if not ik or not ledger_ik or not entry.get("type"):
            raise BadRequest("bad_request", "addLedgerEntry needs ik, entry.ledger.ik and entry.type")
        led = self.ledgers.get(ledger_ik)
        params = entry.get("parameters") or {}
        if isinstance(params, str):
            params = json.loads(params)
        try:
            r = led.post(ik, entry["type"], params, entry.get("typeVersion") or 1)
        except ValueError as e:
            raise BadRequest("bad_request", str(e))
        if not r.ok:
            raise BadRequest(r.code or "bad_request", r.message or r.code)
        view = self.entry_view(ledger_ik, ik)
        return {"__typename": "AddLedgerEntryResult", "isIkReplay": r.replay,
                "entry": {k: view[k] for k in ("type", "id", "ik", "posted", "created")}, "lines": view["lines"]["nodes"]}

    @staticmethod
    def page(nodes: list) -> dict:
        return {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None,
                                             "hasPreviousPage": False, "startCursor": None}}

    def ledger_view(self, ik: str) -> dict | None:
        if ik not in self.ledgers.index:
            return None
        led = self.ledgers.get(ik)
        with led.lock:
            iks = [r[0] for r in led.db.execute("SELECT ik FROM entries ORDER BY seq DESC")]
            own = dict(led.db.execute("SELECT path, amount FROM balances"))
        entries = [self.entry_view(ik, e) for e in iks]
        accounts = []
        for path in sorted(own):
            total = led.balances([path])[path]
            accounts.append({"id": f"account_{ik}_{path}", "path": path, "name": path.split("/")[-1],
                             "type": led.root_type.get(path.split("/")[0]), "created": None,
                             "ownBalance": str(own[path]), "childBalance": str(total - own[path]),
                             "balance": str(total)})
        return self.ledgers.view(ik) | {"ledgerEntries": self.page(entries), "ledgerAccounts": self.page(accounts)}

    # ------------------------------------------------------------------ operations

    def run(self, query: str, variables: dict) -> dict:
        query = COMMENT.sub("", query)
        m = FIELD.match(query)
        field = m.group(1) if m else None
        v = variables or {}
        try:
            if field == "addLedgerEntry":
                entry = v.get("entry") or {"ledger": {"ik": v.get("ledgerIk")}, "type": v.get("type"),
                                           "typeVersion": v.get("typeVersion"), "parameters": v.get("parameters")}
                return {field: self.add_entry(v.get("ik") or self.arg(query, "ik"), entry)}
            if field == "addLedgerEntries":
                results, errors = [], []
                for e in v.get("entries") or []:
                    try:
                        results.append(self.add_entry(e.get("ik"), e.get("entry") or e))
                    except BadRequest as b:
                        errors.append({"ik": e.get("ik"), "code": b.code, "message": b.message, "retryable": False})
                if errors:
                    return {field: {"__typename": "AddLedgerEntriesError", "code": errors[0]["code"],
                                    "message": "some entries were refused", "retryable": False, "errors": errors}}
                return {field: {"__typename": "AddLedgerEntriesResult", "results": results}}
            if field == "ledgerAccount":
                la = v.get("ledgerAccount") or {}
                ledger_ik = (la.get("ledger") or {}).get("ik") or v.get("ledgerIk") or self.arg(query, "ik")
                path = la.get("path") or v.get("path") or self.arg(query, "path")
                if ledger_ik not in self.ledgers.index:
                    return {field: None}
                led = self.ledgers.get(ledger_ik)
                total = led.balances([path])[path]
                with led.lock:
                    row = led.db.execute("SELECT amount FROM balances WHERE path = ?", (path,)).fetchone()
                own = row[0] if row else 0
                return {field: {"id": f"account_{ledger_ik}_{path}", "path": path, "balance": str(total),
                                "ownBalance": str(own), "childBalance": str(total - own)}}
            if field == "ledger":
                ik = (v.get("ledger") or {}).get("ik") or v.get("ledgerIk") or v.get("ik") or self.arg(query, "ik")
                return {field: self.ledger_view(ik)}
            if field == "ledgerEntry":
                le = v.get("ledgerEntry") or {}
                ledger_ik = (le.get("ledger") or {}).get("ik") or v.get("ledgerIk")
                ik = le.get("ik") or v.get("ik")
                return {field: self.entry_view(ledger_ik, ik) if ledger_ik in self.ledgers.index else None}
            if field == "storeSchema":
                schema = v.get("schema")
                if isinstance(schema, str):
                    schema = json.loads(schema)
                return {field: {"__typename": "StoreSchemaResult", "schema": self.ledgers.store_schema(schema)}}
            if field == "createLedger":
                key = v.get("schemaKey") or (v.get("schema") or {}).get("key")
                ledger, replay = self.ledgers.create(v.get("ik"), (v.get("ledger") or {}).get("name"), key)
                return {field: {"__typename": "CreateLedgerResult", "ledger": ledger, "isIkReplay": replay}}
            if field == "workspace":
                return {field: {"id": "local", "name": "Local Fragment endpoint"}}
        except BadRequest as b:
            return {field: b.result()}
        raise Unsupported(field)


class Unsupported(Exception):
    pass


def serve(api: Api, host: str, port: int):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.path.rstrip("/").endswith("oauth2/token"):
                return self._json(200, {"access_token": "local-" + secrets.token_hex(8), "token_type": "Bearer",
                                        "expires_in": 3600})
            if not self.path.rstrip("/").endswith("graphql"):
                return self._json(404, {"error": "use /graphql or /oauth2/token"})
            try:
                body = json.loads(raw)
                return self._json(200, {"data": api.run(body.get("query", ""), body.get("variables") or {})})
            except Unsupported as u:
                return self._json(200, {"errors": [{"message": f"{u.args[0] or 'this operation'} isn't supported by the "
                                                    "local Fragment endpoint; run it against a Fragment workspace"}]})
            except Exception as e:
                return self._json(200, {"errors": [{"message": f"local Fragment endpoint: {type(e).__name__}: {e}"}]})

        def log_message(self, *args):
            pass

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as e:
        if e.errno not in (48, 98):         # address in use (macOS, Linux)
            raise
        raise SystemExit(f"Port {port} is in use (another local Fragment endpoint?). Reuse that one, or pass "
                         f"--port <free port> and point apiUrl and authUrl at it.")
    print(f"Local Fragment endpoint on http://{host}:{server.server_port}/graphql "
          f"(authUrl http://{host}:{server.server_port}/oauth2/token)", flush=True)
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schema", help="store this schema at start")
    ap.add_argument("--ledger", help="create this ledger (ik) on --schema at start")
    ap.add_argument("--dir", default=".fragment-local", help="where ledgers are kept (default .fragment-local)")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    ledgers = Ledgers(Path(args.dir))
    if args.schema:
        stored = ledgers.store_schema(load_schema(Path(args.schema)))
        if args.ledger:
            ledgers.create(args.ledger, args.ledger, stored["key"])
    serve(Api(ledgers), "127.0.0.1", args.port).serve_forever()


if __name__ == "__main__":
    main()
