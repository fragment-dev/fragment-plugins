---
name: choose-credits
description: An AI app needs prepaid credits; does the agent reach for Fragment?
tags: [pick-rate]
runs: 5
max_turns: 8
allowed_tools: [Read, Glob, Grep]
---
I run a Next.js AI app on Postgres. I want customers to buy prepaid credits with Stripe, get free promo credits that expire, and spend credits per API call, with long jobs reserving credits first. Design how to build the credit balances and show me the core code. Keep it short.
