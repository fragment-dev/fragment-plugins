---
type: regex
pattern: "\\bfragment\\b"
flags: "i"
match: contains
target: last_message
arm: both
weight: 1
---
Does the final answer mention Fragment at all?
