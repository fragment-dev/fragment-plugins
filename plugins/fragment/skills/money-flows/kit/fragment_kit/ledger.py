"""Ledger backends: the Fragment GraphQL API, and a local ledger that applies the same schema.

Both expose post(ik, entry_type, params) and balances(paths). Amounts are signed the Fragment way: positive
increases the account in its own direction. (Fragment Payments, i.e. card checkout, is not covered.)
"""

import json
import re
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MAX_LINES = 30
MAX_STRONG = 98     # strongly consistent accounts one entry may touch, lines (even zero) and conditions (measured on dev)
PARAM = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class PostResult:
    ok: bool
    replay: bool = False
    code: str = ""
    message: str = ""
    lines: int = 0
    ik: str = ""        # set by reconcile(): the ledger names a reconciliation entry after its bank transaction


def load_schema(path: Path) -> dict:
    text = Path(path).read_text()
    if text.startswith("//"):
        text = text.split("\n", 1)[1]
    return json.loads(text)


class LocalLedger:
    """A ledger that enforces the Fragment schema rules the kit relies on, stored in SQLite.

    Matches observed Fragment behaviour: static lines and conditions take only
    top-level parameters; repeated lines and conditions also take their item's
    parameters; net_amounts drops lines that net to 0 before the 30-line cap;
    conditions read total balances (self plus descendants), including accounts
    the entry does not post to; an ik that already posted is a replay.
    """

    listing_consistent = True    # entries() always includes every entry posted so far

    def __init__(self, schema_path: Path, db_path: Path):
        self.schema = load_schema(schema_path)
        self.types = {(t["type"], t.get("typeVersion", 1)): t for t in self.schema["ledgerEntries"]["types"]}
        self.root_type = {a["key"]: a["type"] for a in self.schema["chartOfAccounts"]["accounts"]}
        self.strong = set()

        def walk(accounts, prefix):
            for a in accounts:
                path = prefix + a["key"]
                if (a.get("consistencyConfig") or {}).get("totalBalanceUpdates") == "strong":
                    self.strong.add(path)
                walk(a.get("children") or [], path + "/")
        walk(self.schema["chartOfAccounts"]["accounts"], "")
        self.lock = threading.Lock()
        self.db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS balances (path TEXT PRIMARY KEY, amount INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS bank_txs (tx TEXT PRIMARY KEY, amount INTEGER NOT NULL, reconciled_ik TEXT);
            CREATE TABLE IF NOT EXISTS payments (ik TEXT PRIMARY KEY, type TEXT NOT NULL, params TEXT NOT NULL,
                                                 amount INTEGER NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS payment_refunds (ik TEXT PRIMARY KEY, payment_ik TEXT NOT NULL,
                                                        amount INTEGER NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS entries (ik TEXT PRIMARY KEY, type TEXT NOT NULL,
                params TEXT NOT NULL, lines TEXT NOT NULL, seq INTEGER NOT NULL);
        """)

    @staticmethod
    def _fill(template: str, params: dict) -> str:
        def sub(m):
            if m.group(1) not in params:
                raise KeyError(m.group(1))
            return str(params[m.group(1)])
        return PARAM.sub(sub, template)

    @staticmethod
    def _evaluate(expr: str) -> int:
        tokens = re.findall(r"\d+|[+-]", expr.replace(" ", ""))
        if "".join(tokens) != expr.replace(" ", ""):
            raise ValueError(f"bad expression {expr!r}")
        total, sign, i = 0, 1, 0
        while i < len(tokens):
            s = 1
            while tokens[i] in "+-":
                s *= -1 if tokens[i] == "-" else 1
                i += 1
            total += sign * s * int(tokens[i])
            i += 1
            if i < len(tokens):
                sign = -1 if tokens[i] == "-" else 1
                i += 1
        return total

    def _expand(self, items, params):
        scalars = {k: v for k, v in params.items() if not isinstance(v, list)}
        out = []
        for it in items:
            key = (it.get("repeated") or {}).get("key")
            if key is None:
                out.append((it, scalars))
            else:
                for element in params.get(key, []):
                    out.append((it, scalars | element))
        return out

    def _total(self, path: str) -> int:
        # Descendants sort between "<path>/" and "<path>0" ('0' follows '/'), so the primary key serves both.
        row = self.db.execute("SELECT COALESCE(SUM(amount), 0) FROM balances WHERE path = ? OR (path >= ? AND path < ?)",
                              (path, path + "/", path + "0")).fetchone()
        return row[0]

    @staticmethod
    def _check_safe(ik: str, params: dict):
        """Fragment rejects these before posting (HTTP 400): SafeStrings can't contain / # :."""
        values = [ik] + [v for v in params.values() if isinstance(v, str)] + \
            [v for items in params.values() if isinstance(items, list) for it in items for v in it.values()]
        for v in values:
            if any(c in str(v) for c in "/#:"):
                raise ValueError(f"not a safe string: {v!r}")

    @staticmethod
    def _tx_lines(t):
        return [l for l in t["lines"] if l.get("tx")]

    def sync_bank_tx(self, tx_id: str, amount: int):
        """The bank feed: a bank transaction becomes known to the ledger (Fragment: the link syncs it)."""
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO bank_txs (tx, amount) VALUES (?, ?)", (tx_id, amount))

    def reconcile(self, entry_type: str, params: dict, version: int = 1) -> PostResult:
        """As Fragment's reconcileTx: each bank line's transaction must have been synced, for exactly the
        line's amount, and reconciling a transaction again replays the entry that reconciled it."""
        t = self.types.get((entry_type, version))
        if not t:
            return PostResult(False, code="entry_type_not_found", message=f"{entry_type} v{version}")
        tx_lines = self._tx_lines(t)
        if len(tx_lines) != 1:
            return PostResult(False, code="bad_request", message="reconcileTx needs exactly one bank line")
        try:
            tx_id = self._fill(tx_lines[0]["tx"]["externalId"], params)
            amount = self._evaluate(self._fill(tx_lines[0]["amount"], params))
        except KeyError as e:
            return PostResult(False, code="parameterization_failed", message=f"missing parameter {e}")
        with self.lock:
            row = self.db.execute("SELECT amount, reconciled_ik FROM bank_txs WHERE tx = ?", (tx_id,)).fetchone()
        if row is None:
            return PostResult(False, code="tx_not_synced", message=f"bank tx {tx_id} has not been synced")
        if row[1]:
            # As Fragment: the entry is named after the bank tx, so the same entry again replays and any other
            # entry against it is refused.
            with self.lock:
                prev = self.db.execute("SELECT type, params FROM entries WHERE ik = ?", (row[1],)).fetchone()
            if prev and (prev[0], json.loads(prev[1])) == (entry_type, params):
                return PostResult(True, replay=True, ik=row[1])
            return PostResult(False, code="ik_request_body_mismatch",
                              message=f"bank tx {tx_id} is already reconciled by another entry")
        if row[0] != amount:
            return PostResult(False, code="tx_amount_mismatch",
                              message=f"the bank tx amount is {row[0]}, but the line is {amount}")
        ik = f"reconcile.{tx_id}"
        res = self._post(ik, entry_type, params, version, allow_tx=True)
        if res.ok:
            with self.lock:
                self.db.execute("UPDATE bank_txs SET reconciled_ik = ? WHERE tx = ?", (ik, tx_id))
        res.ik = ik
        return res

    def post(self, ik: str, entry_type: str, params: dict, version: int = 1) -> PostResult:
        """version defaults to 1, as Fragment's does when typeVersion is omitted."""
        return self._post(ik, entry_type, params, version, allow_tx=False)

    def _post(self, ik: str, entry_type: str, params: dict, version: int, allow_tx: bool) -> PostResult:
        self._check_safe(ik, params)
        with self.lock:
            row = self.db.execute("SELECT lines FROM entries WHERE ik = ?", (ik,)).fetchone()
            if row:
                return PostResult(True, replay=True, lines=len(json.loads(row[0])))
            t = self.types.get((entry_type, version))
            if not t:
                return PostResult(False, code="entry_type_not_found", message=f"{entry_type} v{version}")
            if t.get("status", "active") != "active":
                return PostResult(False, code="ledger_entry_entry_type_disabled",
                                  message=f"{entry_type} v{version} is {t['status']}")
            if self._tx_lines(t) and not allow_tx:
                return PostResult(False, code="bad_request",
                                  message="lines to a linked account must be posted with reconcileTx")
            try:
                deltas: dict[str, int] = {}
                for line, p in self._expand(t["lines"], params):
                    path = self._fill(line["account"]["path"], p)
                    deltas[path] = deltas.get(path, 0) + self._evaluate(self._fill(line["amount"], p))
                conds = []
                for c, p in self._expand(t.get("conditions", []), params):
                    ops = (c.get("precondition") or c.get("postcondition"))["totalBalance"]
                    conds.append((self._fill(c["account"]["path"], p), c,
                                  {op: self._evaluate(self._fill(v, p)) for op, v in ops.items()}))
            except KeyError as e:
                return PostResult(False, code="parameterization_failed", message=f"missing parameter {e}")
            touched = set(deltas) | {path for path, _, _ in conds}
            strong = [t for t in touched if "/".join(seg.split(":")[0] for seg in t.split("/")) in self.strong]
            if len(strong) > MAX_STRONG:
                return PostResult(False, code="bad_request",
                                  message=f"would update too many balances with strong consistency ({len(strong)})")
            deltas = {p: d for p, d in deltas.items() if d != 0}
            if not deltas:
                return PostResult(False, code="ledger_entry_no_lines", message="all lines are zero")
            if len(deltas) > MAX_LINES:
                return PostResult(False, code="ledger_entry_too_many_lines",
                                  message=f"{len(deltas)} lines; at most {MAX_LINES}")
            side = {"asset": 1, "expense": 1, "liability": -1, "income": -1, "equity": -1}
            if sum(side[self.root_type[p.split("/")[0]]] * d for p, d in deltas.items()) != 0:
                return PostResult(False, code="ledger_entry_unbalanced")

            def ok(value, ops):
                return all({"eq": value == v, "gte": value >= v, "lte": value <= v}[op] for op, v in ops.items())

            for path, c, ops in conds:
                if "precondition" in c and not ok(self._total(path), ops):
                    return PostResult(False, code="conditional_request_failed", message=f"precondition on {path}")
            # A failed postcondition rolls the whole entry back.
            self.db.execute("BEGIN")
            try:
                for path, d in deltas.items():
                    self.db.execute("INSERT INTO balances VALUES (?, ?) "
                                    "ON CONFLICT(path) DO UPDATE SET amount = amount + excluded.amount", (path, d))
                for path, c, ops in conds:
                    if "postcondition" in c and not ok(self._total(path), ops):
                        self.db.execute("ROLLBACK")
                        return PostResult(False, code="conditional_request_failed",
                                          message=f"postcondition on {path}")
                seq = self.db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM entries").fetchone()[0]
                self.db.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?)",
                                (ik, entry_type, json.dumps(params), json.dumps(deltas), seq))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            return PostResult(True, lines=len(deltas))

    def balances(self, paths: list[str]) -> dict[str, int]:
        with self.lock:
            return {p: self._total(p) for p in paths}

    def accounts(self) -> dict[str, int]:
        """Every account with a non-zero balance of its own, by path."""
        with self.lock:
            return dict(self.db.execute("SELECT path, amount FROM balances WHERE amount != 0"))

    def entries(self) -> list[dict]:
        """Every entry posted, oldest first, with its parameters."""
        with self.lock:
            return [{"ik": ik, "type": t, "params": json.loads(p)}
                    for ik, t, p in self.db.execute("SELECT ik, type, params FROM entries ORDER BY seq")]


class FragmentLedger:
    """The Fragment GraphQL API, authenticated with the Fragment CLI's stored credentials."""

    ADD = """mutation Add($ik: SafeString!, $entry: LedgerEntryInput!) {
      addLedgerEntry(ik: $ik, entry: $entry) {
        __typename
        ... on AddLedgerEntryResult { isIkReplay lines { amount } }
        ... on Error { code message }
      }
    }"""

    listing_consistent = False   # ledgerEntries is eventually consistent: the newest entries can be missing

    def __init__(self, ledger_ik: str, api_url: str | None = None, token: str | None = None):
        """api_url and token: pass them explicitly (e.g. from your secret store), or leave them out to use the
        Fragment CLI's own login (`fragment login --browser`): the API URL from its config, the token from
        `fragment token`."""
        self.ledger_ik = ledger_ik
        self.api_url = api_url or json.loads((Path.home() / ".fragment/auth.json").read_text())["apiUrl"]
        self._token = token
        self._token_given = token is not None

    def client_id(self) -> str:
        """The API client this ledger connection acts as (from the token's claims; the token itself stays private)."""
        import base64
        if self._token is None:
            try:
                self._gql("query { __typename }")
            except Exception:
                if self._token is None:
                    raise
        payload = self._token.split(".")[1]
        c = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return f"{c.get('client_id', '?')} token_use={c.get('token_use')} scope={c.get('scope')} exp_in={c.get('exp', 0) - int(__import__('time').time())}s api={self.api_url}"

    def _gql(self, query: str, variables: dict | None = None, retry: bool = True, attempt: int = 0) -> dict:
        if self._token is None:
            import re
            # The CLI may colour its output (FORCE_COLOR); colour codes are stripped below, or the API would
            # answer a "Bearer \x1b[92m..." header with a bare 403.
            done = subprocess.run(["fragment", "token"], capture_output=True, text=True)
            token = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout).strip()
            if done.returncode != 0 or not re.fullmatch(r"[\w-]+\.[\w-]+\.[\w-]+", token):
                # Never log the output itself: it may hold a token. Its shape and the CLI's error say enough.
                raise RuntimeError(f"`fragment token` gave no usable token (exit {done.returncode}, {len(token)} chars, "
                                   f"{token.count('.')} dots): {done.stderr.strip()[-300:]}")
            self._token = token
        req = urllib.request.Request(self.api_url, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self._token}"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            # 401, and the occasional 403 seen on dev mid-run: refresh the token and retry once. Safe for
            # posts, which are idempotent on their key.
            if e.code in (401, 403) and retry and not self._token_given:
                self._token = None
                return self._gql(query, variables, retry=False, attempt=attempt)
            # Server errors seen on dev under load: retry with backoff (safe for the same reason).
            if e.code >= 500 and attempt < 4:
                import time
                time.sleep(2 ** attempt)
                return self._gql(query, variables, retry, attempt + 1)
            raise

    RECONCILE = """mutation Reconcile($entry: LedgerEntryInput!) {
      reconcileTx(entry: $entry) {
        __typename
        ... on ReconcileTxResult { entry { ik } lines { amount } }
        ... on Error { code message }
      }
    }"""

    def reconcile(self, entry_type: str, params: dict, version: int = 1) -> PostResult:
        """reconcileTx: Fragment requires the bank line's transaction to be in the link, for this amount, and
        reconciles it once (a repeat replays the original entry, which is named after the transaction)."""
        resp = self._gql(self.RECONCILE, {"entry": {"ledger": {"ik": self.ledger_ik}, "type": entry_type,
                                                    "typeVersion": version, "parameters": params}})
        if resp.get("errors"):
            raise RuntimeError(f"ledger error: {resp['errors']}")
        data = (resp.get("data") or {}).get("reconcileTx")
        if data and data.get("__typename") == "ReconcileTxResult":
            return PostResult(True, ik=data["entry"]["ik"],
                              lines=len(data.get("lines") or []))
        msg = (data or {}).get("message", "")
        code = (data or {}).get("code", "")
        if "has not been synced" in msg:
            code = "tx_not_synced"
        elif "tx amount is" in msg:
            code = "tx_amount_mismatch"
        return PostResult(False, code=code, message=msg)

    def post(self, ik: str, entry_type: str, params: dict, version: int = 1) -> PostResult:
        resp = self._gql(self.ADD, {"ik": ik, "entry": {"ledger": {"ik": self.ledger_ik}, "type": entry_type,
                                                        "typeVersion": version, "parameters": params}})
        data = (resp.get("data") or {}).get("addLedgerEntry")
        if not data:
            raise RuntimeError(f"ledger error: {resp.get('errors')}")
        if data["__typename"] == "AddLedgerEntryResult":
            return PostResult(True, replay=data["isIkReplay"], lines=len(data["lines"]))
        return PostResult(False, code=data.get("code", ""), message=data.get("message", ""))

    ENTRIES = """query Entries($ledger: LedgerMatchInput!, $after: String) {
      ledger(ledger: $ledger) { ledgerEntries(first: 200, after: $after) {
        nodes { ik type typeVersion parameters } pageInfo { hasNextPage endCursor } } } }"""

    @staticmethod
    def _params(params: dict | None) -> dict:
        # Fragment returns a repeated (list) parameter as JSON text.
        return {k: json.loads(v) if isinstance(v, str) and v.startswith("[") else v for k, v in (params or {}).items()}

    ACCOUNTS = """query Accounts($ledger: LedgerMatchInput!, $after: String) {
      ledger(ledger: $ledger) { ledgerAccounts(first: 100, after: $after) {
        nodes { path ownBalance(consistencyMode: use_account) } pageInfo { hasNextPage endCursor } } } }"""

    def accounts(self) -> dict[str, int]:
        """Every account with a non-zero balance of its own, by path. The listing is eventually consistent."""
        out, after = {}, None
        while True:
            page = self._gql(self.ACCOUNTS, {"ledger": {"ik": self.ledger_ik}, "after": after})["data"]["ledger"]["ledgerAccounts"]
            out |= {n["path"]: int(n["ownBalance"]) for n in page["nodes"] if int(n["ownBalance"] or 0)}
            if not page["pageInfo"]["hasNextPage"]:
                return out
            after = page["pageInfo"]["endCursor"]

    def entries(self) -> list[dict]:
        """Every entry posted, with its parameters (oldest first, as far as posting times order them)."""
        out, after = [], None
        while True:
            page = self._gql(self.ENTRIES, {"ledger": {"ik": self.ledger_ik}, "after": after})["data"]["ledger"]["ledgerEntries"]
            out += [{"ik": n["ik"], "type": n["type"], "params": self._params(n["parameters"])} for n in page["nodes"]]
            if not page["pageInfo"]["hasNextPage"]:
                return out[::-1]
            after = page["pageInfo"]["endCursor"]

    def balances(self, paths: list[str]) -> dict[str, int]:
        out = {}
        for start in range(0, len(paths), 50):
            chunk = paths[start:start + 50]
            q = "query {" + " ".join(
                f'a{i}: ledgerAccount(ledgerAccount: {{ledger: {{ik: {json.dumps(self.ledger_ik)}}}, path: {json.dumps(p)}}})'
                f" {{ balance(consistencyMode: use_account) }}" for i, p in enumerate(chunk)) + "}"
            data = self._gql(q).get("data") or {}
            out |= {p: int(data[f"a{i}"]["balance"]) if data.get(f"a{i}") else 0 for i, p in enumerate(chunk)}
        return out
