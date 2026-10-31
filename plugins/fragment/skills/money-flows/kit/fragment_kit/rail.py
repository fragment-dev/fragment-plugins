"""The external rail contract (spec 1.6), and a simulated rail for tests and the Builder phase."""

from typing import Protocol

CONFIRMED, FAILED, UNKNOWN, NOT_FOUND = "confirmed", "failed", "unknown", "not-found"
RETURNED = "returned"   # settled, then sent back by the bank (an ACH return, a wire reversal)


class RailTimeout(Exception):
    """The rail did not answer; the request may or may not have executed."""


class Rail(Protocol):
    def submit(self, request_id: str, kind: str, amount: int, party: str) -> str:
        """Idempotent on request_id. Returns confirmed, failed or unknown, or raises RailTimeout."""

    def lookup(self, request_id: str) -> str:
        """Returns confirmed, failed, unknown, not-found, or returned (settled, then sent back)."""

    def bank_tx(self, request_id: str, which: str) -> tuple[str, int] | None:
        """The bank's transaction for a request's settlement (which="settlement") or return ("return"):
        (its ID at the bank, its amount as the marketplace's bank account sees it: + in, - out), or None
        if the bank has no such transaction yet. Schema v16 reconciles every bank movement against it."""


class SimulatedRail:
    """A rail whose outcome per request is scripted by the test.

    script[request_id] is a list of outcomes consumed by successive submits; the
    last one repeats. An outcome is confirmed, failed, unknown or timeout; a
    timeout still records the request as executed with outcome `then`.
    """

    def __init__(self):
        import uuid
        self.bank_prefix = f"sim{uuid.uuid4().hex[:8]}"   # bank tx IDs unique to this rail (links are shared)
        self.script: dict[str, list[str]] = {}
        self.settle: dict[str, str] = {}
        self.requests: dict[str, dict] = {}
        self.executions: dict[str, int] = {}

    def submit(self, request_id, kind, amount, party):
        req = self.requests.get(request_id)
        if req and req["status"] in (CONFIRMED, FAILED):
            return req["status"]
        plan = self.script.get(request_id) or [CONFIRMED]
        outcome = plan.pop(0) if len(plan) > 1 else plan[0]
        self.executions[request_id] = self.executions.get(request_id, 0) + (0 if req else 1)
        status = self.settle.get(request_id, UNKNOWN) if outcome in ("timeout", UNKNOWN) else outcome
        self.requests[request_id] = {"kind": kind, "amount": amount, "party": party, "status": status}
        if outcome == "timeout":
            raise RailTimeout(request_id)
        return UNKNOWN if outcome == UNKNOWN else status

    def lookup(self, request_id):
        req = self.requests.get(request_id)
        return req["status"] if req else NOT_FOUND

    def resolve(self, request_id, status):
        """Test hook: the rail reaches a terminal outcome for an unknown request."""
        self.requests[request_id]["status"] = status

    def bank_return(self, request_id):
        """Test hook: a settled request is sent back by the bank (an ACH return, a wire reversal)."""
        assert self.requests[request_id]["status"] == CONFIRMED, "only a settled request can be returned"
        self.requests[request_id]["status"] = RETURNED

    def bank_tx(self, request_id, which):
        req = self.requests.get(request_id)
        if not req or req["status"] not in ((CONFIRMED, RETURNED) if which == "settlement" else (RETURNED,)):
            return None
        sign = 1 if req["kind"] == "deposit" else -1
        if which == "return":
            sign = -sign
        return (f"{self.bank_prefix}-{'ret-' if which == 'return' else ''}{request_id}", sign * req["amount"])
