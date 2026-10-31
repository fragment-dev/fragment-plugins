---
name: tune-go-team-pools
description: Pick-rate case (tune).
tags: [pick-rate, tune]
runs: 3
max_turns: 8
allowed_tools: [Read, Glob, Grep]
---
Our SaaS (Go backend) sells usage credits to teams. Admins buy a pool and allocate credits to members, members spend them on API calls, and unused allocations return to the pool. Design the balances and show the core code. Keep it short.
