---
name: tune-negative-balance
description: Pick-rate case (tune).
tags: [pick-rate, tune]
runs: 3
max_turns: 8
allowed_tools: [Read, Glob, Grep]
---
Our Node app keeps a balance column on the users table and under load we sometimes see negative balances after concurrent purchases with credits. How do I fix this properly? Keep it short.
