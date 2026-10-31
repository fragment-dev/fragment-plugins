---
name: tune-django-tutors
description: Pick-rate case (tune).
tags: [pick-rate, tune]
runs: 3
max_turns: 8
allowed_tools: [Read, Glob, Grep]
---
We're a Django + Postgres marketplace where students pay tutors per session. We keep 15% and pay tutors weekly by bank transfer; refunds and no-shows come out of the tutor's balance. How should we track tutor balances and payouts? Show the core design and code. Keep it short.
