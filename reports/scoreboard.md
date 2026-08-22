# MONDAY scoreboard

Generated 2026-08-22 21:31 by `py -3.12 -m reports.scoreboard`.

These numbers trade against each other, which is the reason they are in
one table. Phase 9 raised precision and coverage went *down*, because 25
parses that used to "route" were junk; Phase 11 added a capability and
coverage stayed flat, because new rows entered the denominator at the
same time. Either number alone would have told a wrong story.

| Measure | Value | Detail |
|---|---:|---|
| Coverage | **35.2%** | 3,936 of 11,180 real utterances reach a skill |
| Precision | **88%** | 7/8 correctly refused; reached: delete all my photos → recall_memory |
| Capability | **68** | 57 work offline, 7,419 patterns, 1 behind the Tier-2 gate |
| Suite | **green** | 1038 passed, 7 deselected in 63.03s (0:01:03) (66s) |

**Not measured here: task success** — whether a routed command then
worked end to end. It needs a fixture that can exercise irreversible
skills safely, and a weak version invented to fill the row would be
worse than the row being honestly absent.
