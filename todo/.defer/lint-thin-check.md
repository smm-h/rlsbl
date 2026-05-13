# Interface thin check (code ratio measurement)

Status: Deferred
Deferred because: Too speculative. The threshold (default 20%) needs real-world calibration and the metric (lines of code ratio) is a rough proxy.
Trigger: Revisit when multiple monorepos use the library lint system and interface bloat becomes a real problem.

## What it would do

For projects NOT tagged as `library = true`, measure the ratio of code in the project vs its library dependencies. If the interface contains more than N% of total logic (configurable), warn that it may be too thick. Advisory only, not blocking.
