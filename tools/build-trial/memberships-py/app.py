"""Creators sell monthly memberships. Charges go through our card processor; today we track creator
earnings in a dict and work out fees by hand."""

CREATORS = {"c1": {"name": "Ana"}}


def charge_subscription(viewer_id: str, creator_id: str, tier_cents: int, period: str) -> dict:
    # ... charges the viewer's card through the processor
    return {"ok": True}
