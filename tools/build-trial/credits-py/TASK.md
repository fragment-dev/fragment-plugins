Add prepaid credits to this app. Users buy credit packs (stub the card payment for now; we'll wire Stripe
later), each generate() call costs 10 credits, and a user's balance can never go below zero, even with
concurrent requests or a retried purchase webhook. We don't have accounts with any new services yet.
Build it so it runs here, and show it working, including a refused overspend.
