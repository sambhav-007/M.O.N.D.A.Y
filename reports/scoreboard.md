# MONDAY scoreboard

Generated 2026-10-19 14:14 by `py -3.12 -m reports.scoreboard`.

These numbers trade against each other, which is the reason they are in
one table. Phase 9 raised precision and coverage went *down*, because 25
parses that used to "route" were junk; Phase 11 added a capability and
coverage stayed flat, because new rows entered the denominator at the
same time. Either number alone would have told a wrong story.

| Measure | Value | Detail |
|---|---:|---|
| Coverage | **35.2%** | 3,932 of 11,180 real utterances reach a skill |
| Precision | **100%** | 8/8 correctly refused |
| Capability | **73** | 61 work offline, 8,156 patterns, 2 behind the Tier-2 gate |
| Task success | **100%** | 20/20 tasks completed end to end |
| Suite | **green** | 1105 passed, 7 deselected in 68.95s (0:01:08) (73s) |

**Task success** runs each command and checks the outcome, not the
routing decision — see `reports/task_success.md` for the set and for
what it deliberately does not measure (sending mail, killing processes,
anything that cannot be run twice safely).
