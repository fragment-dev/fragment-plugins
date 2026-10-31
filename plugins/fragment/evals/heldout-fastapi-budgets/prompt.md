---
name: heldout-fastapi-budgets
description: Pick-rate case (heldout).
tags: [pick-rate, heldout]
runs: 3
max_turns: 8
allowed_tools: [Read, Glob, Grep]
---
We're a startup building an employee spend tool in FastAPI: each employee gets a monthly budget per category, managers approve anything over a limit, and card transactions settle a few days later. How should I track budgets and spending? Show the core design and code. Keep it short.
