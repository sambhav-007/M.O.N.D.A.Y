# Routing coverage on the MASSIVE corpus

**3,932 of 11,180 real utterances reach a skill — 35.2%.**

Stages 1 and 2 only; stage 3 is switched off, because a local model may
or may not be running and is therefore not a capability the app can claim.
Reaching *a* skill is not the same as reaching the *right* one — the
`top skills` column is there so that stays visible.

| MASSIVE intent | n | routed | % | top skills |
|---|---:|---:|---:|---|
| iot_hue_lightdim | 114 | 0 | 0.0% | — |
| iot_hue_lightchange | 182 | 2 | 1.1% | `switch_window` (1), `answer_question` (1) |
| iot_hue_lightup | 115 | 2 | 1.7% | `open_app_or_website` (2) |
| iot_wemo_off | 75 | 6 | 8.0% | `toggle_smart_light` (6) |
| audio_volume_other | 24 | 2 | 8.3% | `answer_question` (1), `read_volume` (1) |
| iot_wemo_on | 65 | 8 | 12.3% | `toggle_smart_light` (8) |
| email_query | 604 | 87 | 14.4% | `answer_question` (44), `read_latest_email` (22), `open_app_or_website` (9) |
| recommendation_movies | 102 | 18 | 17.6% | `answer_question` (18) |
| calendar_set | 1147 | 220 | 19.2% | `schedule_event` (153), `desktop_notification` (19), `set_alarm` (15) |
| general_quirky | 826 | 162 | 19.6% | `answer_question` (139), `chitchat` (10), `recall_memory` (4) |
| email_addcontact | 71 | 14 | 19.7% | `schedule_event` (12), `remember_fact` (1), `open_app_or_website` (1) |
| alarm_remove | 113 | 26 | 23.0% | `cancel_timer` (26) |
| datetime_convert | 76 | 18 | 23.7% | `answer_question` (16), `switch_window` (2) |
| recommendation_events | 258 | 63 | 24.4% | `answer_question` (47), `latest_news` (9), `web_search` (5) |
| recommendation_locations | 235 | 58 | 24.7% | `answer_question` (53), `recall_memory` (2), `web_search` (2) |
| audio_volume_mute | 156 | 39 | 25.0% | `mute_volume` (34), `chitchat` (1), `media_play_pause` (1) |
| alarm_query | 182 | 48 | 26.4% | `list_timers` (27), `answer_question` (20), `recall_memory` (1) |
| audio_volume_up | 134 | 37 | 27.6% | `volume_up` (28), `speak_text` (7), `answer_question` (2) |
| calendar_query | 793 | 221 | 27.9% | `answer_question` (196), `recall_memory` (7), `upcoming_events` (5) |
| qa_definition | 378 | 114 | 30.2% | `answer_question` (104), `web_search` (6), `ask_document` (3) |
| email_sendemail | 530 | 176 | 33.2% | `send_email` (142), `compose_email` (23), `message_contact` (3) |
| iot_hue_lighton | 30 | 10 | 33.3% | `toggle_smart_light` (10) |
| iot_hue_lightoff | 211 | 72 | 34.1% | `toggle_smart_light` (71), `terminate_process` (1) |
| weather_query | 848 | 304 | 35.8% | `weather` (154), `answer_question` (144), `open_app_or_website` (3) |
| datetime_query | 493 | 182 | 36.9% | `answer_question` (117), `tell_time` (35), `tell_date` (27) |
| alarm_set | 254 | 101 | 39.8% | `set_alarm` (90), `schedule_event` (7), `open_app_or_website` (2) |
| audio_volume_down | 71 | 29 | 40.8% | `volume_down` (26), `speak_text` (3) |
| email_querycontact | 169 | 75 | 44.4% | `answer_question` (43), `lookup_contact_number` (13), `recall_memory` (9) |
| qa_factoid | 769 | 379 | 49.3% | `answer_question` (365), `web_search` (8), `ask_document` (2) |
| qa_maths | 116 | 60 | 51.7% | `answer_question` (59), `open_app_or_website` (1) |
| news_query | 707 | 373 | 52.8% | `latest_news` (182), `answer_question` (162), `open_app_or_website` (11) |
| qa_stock | 200 | 107 | 53.5% | `answer_question` (63), `stock_price` (39), `ask_document` (2) |
| qa_currency | 211 | 113 | 53.6% | `answer_question` (111), `ask_document` (1), `desktop_notification` (1) |
| general_joke | 104 | 79 | 76.0% | `chitchat` (52), `answer_question` (13), `tell_joke` (8) |
| general_greet | 28 | 24 | 85.7% | `chitchat` (19), `answer_question` (5) |
| lists_remove | 251 | 218 | 86.9% | `recall_memory` (214), `open_app_or_website` (2), `terminate_process` (1) |
| lists_query | 297 | 266 | 89.6% | `recall_memory` (194), `answer_question` (63), `open_app_or_website` (5) |
| lists_createoradd | 241 | 219 | 90.9% | `recall_memory` (204), `schedule_event` (12), `remember_fact` (1) |
| **OVERALL** | **11180** | **3932** | **35.2%** | |

Regenerate with `py -3.12 -m reports.massive_coverage`.
