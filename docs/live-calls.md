# Live call log (lab, auto-exported from Postgres + traces)

Exported: 2026-09-20T02:21:00.011478+00:00
Total calls: 263

## pg-8941eff458bd — 2026-09-06 13:44:36.926561+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-test ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:36.928085+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## pg-idem-0bc815f357e0 — 2026-09-06 13:44:36.970303+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-idem ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:36.971966+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## say — 2026-09-06 13:44:40.323020+00:00 (fsm=CALL_START, termination=None)

family=fam-test ended=False
facts={}
observations: 0
key events: 0

## defer — 2026-09-06 13:44:40.482552+00:00 (fsm=FINAL_CLASSIFICATION, termination=DEFERRED)

family=fam-test ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:40.483780+00:00 {"partial": true, "termination_reason": "DEFERRED"}

## wrong — 2026-09-06 13:44:40.507490+00:00 (fsm=FINAL_CLASSIFICATION, termination=WRONG_PERSON)

family=fam-test ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:40.508710+00:00 {"partial": true, "termination_reason": "WRONG_PERSON"}

## consent — 2026-09-06 13:44:40.518386+00:00 (fsm=CALL_START, termination=None)

family=fam-test ended=False
facts={}
observations: 0
key events: 0

## pg-527462ecc106 — 2026-09-06 13:44:40.587692+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-test ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:40.589523+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## pg-idem-00ede56e0bb5 — 2026-09-06 13:44:40.626780+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-idem ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:40.628020+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## audit — 2026-09-06 13:44:40.755677+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_REVOKED)

family=fam-test ended=True
facts={"plans": "весь день буду дома", "sleep": "плохо спала"}
observations: 4
- t2 [wellness] Пока всё хорошо | quote: Пока всё хорошо
- t2 [sleep] плохо спала | quote: плохо спала
- t2 [plans] весь день буду дома | quote: весь день буду дома
- t2 [None] я упала и не могу встать | quote: я упала и не могу встать
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:40.458131+00:00 {"partial": true, "termination_reason": "CONSENT_REVOKED"}

## term — 2026-09-06 13:44:40.794207+00:00 (fsm=FINAL_CLASSIFICATION, termination=None)

family=fam-test ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 13:44:40.795415+00:00 {"partial": true, "termination_reason": null}

## sip-421fbc79df — 2026-09-06 15:12:30.686249+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:12:30.693672+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-f137ff41b9 — 2026-09-06 15:12:54.895514+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:12:54.901070+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-3985072e1d — 2026-09-06 15:14:31.836053+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:14:31.839922+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## media-48defbc1 — 2026-09-06 15:15:24.382730+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:15:24.387179+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## media-ac14d2b2 — 2026-09-06 15:16:04.668050+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-1]: Да, это я.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:16:04.672949+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-7804ea125c — 2026-09-06 15:16:37.144267+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 0

## sip-0800c3410d — 2026-09-06 15:18:24.699496+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 0

## sip-51953e0761 — 2026-09-06 15:23:37.980431+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:23:37.983886+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-926cfc81ba — 2026-09-06 15:24:44.242814+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:24:44.246865+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b115e2258d — 2026-09-06 15:25:51.671442+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:25:51.674662+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b7a50e9cb9 — 2026-09-06 15:27:57.462223+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:27:57.465614+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9c972fcdb9 — 2026-09-06 15:43:54.006833+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 0

## sip-0a94a47d05 — 2026-09-06 15:48:41.534970+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 15:48:41.543828+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-67e737febb — 2026-09-06 17:12:07.870551+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 17:12:07.878108+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ecc9455ec2 — 2026-09-06 17:13:14.413604+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 0

## sip-5085974b40 — 2026-09-06 17:14:01.841362+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 0

## sip-fb37304784 — 2026-09-06 17:17:49.525192+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 17:17:49.528445+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-f1d913bcd9 — 2026-09-06 20:06:08.512092+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 20:06:08.519678+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-d98b9bd3a6 — 2026-09-06 20:20:52.677313+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 20:20:52.683717+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9c081a1acf — 2026-09-06 20:51:49.900642+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 20:51:49.906875+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-3a46ad0ec9 — 2026-09-06 20:53:15.151056+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 20:53:15.155445+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-cf08b1d6fe — 2026-09-06 20:53:50.816821+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 20:53:50.819461+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-08254739f0 — 2026-09-06 20:55:30.052728+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 20:55:30.057630+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-03a8e26a72 — 2026-09-06 21:08:37.015720+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:08:37.019820+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-a66024f7fa — 2026-09-06 21:09:58.980553+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:09:58.983726+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-4fb275716a — 2026-09-06 21:13:39.487942+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:13:39.491132+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-5e71376cd1 — 2026-09-06 21:18:38.906416+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:18:38.912249+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-42c829d3a9 — 2026-09-06 21:19:07.297996+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:19:07.305058+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-6db41a1f74 — 2026-09-06 21:19:19.026849+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:19:19.031913+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-2e5bc8aec8 — 2026-09-06 21:20:23.115847+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:20:23.120174+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-24704f379e — 2026-09-06 21:33:42.228274+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:33:42.372356+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-99de797ab5 — 2026-09-06 21:34:41.363441+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:34:41.365704+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b2e42437e4 — 2026-09-06 21:38:59.236872+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:38:59.239645+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-8e313ca55f — 2026-09-06 21:43:33.125197+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 0

## sip-3fa2420f27 — 2026-09-06 21:59:08.750333+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 21:59:08.755887+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-956145c520 — 2026-09-06 22:21:46.196287+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:21:46.200842+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-906515a8e9 — 2026-09-06 22:23:18.032860+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:23:18.037003+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9606317380 — 2026-09-06 22:23:51.086976+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:23:51.091729+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-74b2db1134 — 2026-09-06 22:24:39.173185+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:24:39.176451+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-e8ba5b2594 — 2026-09-06 22:31:17.071089+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:31:17.074107+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ee14384e11 — 2026-09-06 22:32:32.911886+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:32:32.914118+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-16a64c0b56 — 2026-09-06 22:34:54.125131+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:34:54.129426+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-1aa441cc86 — 2026-09-06 22:44:28.298204+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:44:28.301180+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-2a044fd4e2 — 2026-09-06 22:52:48.298968+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 22:52:48.302079+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-0016cdc5bd — 2026-09-06 23:17:34.288405+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-06 23:17:34.291718+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b5dbbb12df — 2026-09-07 00:03:05.137094+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:03:05.141372+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-bf416eca2a — 2026-09-07 00:22:20.407872+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:22:20.414222+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-271cbbb67f — 2026-09-07 00:37:35.298848+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:37:35.301969+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-45b72499c6 — 2026-09-07 00:39:30.117533+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:39:30.129307+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-d03cd54d75 — 2026-09-07 00:39:58.103936+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:39:58.108223+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-a3d6d9e32f — 2026-09-07 00:43:48.008331+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:43:48.014626+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-c570309cb5 — 2026-09-07 00:45:31.378986+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:45:31.389970+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## e2e-34c91eeb — 2026-09-07 00:46:34.996777+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:46:35.001061+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-39222a6a84 — 2026-09-07 00:50:18.296607+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:50:18.301528+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-340ea83659 — 2026-09-07 00:51:01.360623+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:51:01.364115+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-fe2577c23f — 2026-09-07 00:53:02.956875+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-1]: Вот.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-2]: И.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-3]: В.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-4]: Ну.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-5]: После.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-6]: Ну.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-7]: Д.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-8]: В.
observations: 0
key events: 8
- #2 PLANNER_DECISION 2026-09-07 00:52:13.181573+00:00 {"intent": "confirm_identity", "turn_id": 2, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-1", "state_version...
- #3 PLANNER_DECISION 2026-09-07 00:52:22.849898+00:00 {"intent": "confirm_identity", "turn_id": 3, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-2", "state_version...
- #4 PLANNER_DECISION 2026-09-07 00:52:29.563154+00:00 {"intent": "confirm_identity", "turn_id": 4, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-3", "state_version...
- #5 PLANNER_DECISION 2026-09-07 00:52:35.346639+00:00 {"intent": "confirm_identity", "turn_id": 5, "user_act": "backchannel", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-4", "state_vers...
- #6 PLANNER_DECISION 2026-09-07 00:52:43.570990+00:00 {"intent": "confirm_identity", "turn_id": 6, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-5", "state_version...
- #7 PLANNER_DECISION 2026-09-07 00:52:51.430249+00:00 {"intent": "confirm_identity", "turn_id": 7, "user_act": "backchannel", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-6", "state_vers...
- #8 PLANNER_DECISION 2026-09-07 00:52:59.132218+00:00 {"intent": "confirm_identity", "turn_id": 8, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-7", "state_version...
- #9 CALL_ENDED 2026-09-07 00:53:02.961566+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-4db99c2384 — 2026-09-07 00:57:09.000747+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 00:57:09.005897+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b7257cbdf5 — 2026-09-07 01:00:33.826471+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 01:00:33.833765+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ec7c5f261a — 2026-09-07 01:11:21.694304+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 01:11:21.698421+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-fbd5f14cf6 — 2026-09-07 01:13:35.192585+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 01:13:35.196683+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-2af6c5d27d — 2026-09-07 01:28:37.736875+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 01:28:37.740835+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ae8a649497 — 2026-09-07 02:18:42.935636+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 02:18:42.939066+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-45eca01885 — 2026-09-07 13:50:25.994813+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 13:50:25.998319+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-e35132246e — 2026-09-07 13:51:16.326227+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 13:51:16.330132+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-3f95641c5b — 2026-09-07 13:52:46.645501+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 13:52:46.650535+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-cdeeb202ed — 2026-09-07 13:54:29.729238+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 13:54:29.732372+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-e912f033be — 2026-09-07 13:56:42.817354+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 13:56:42.819939+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-408e3037fa — 2026-09-07 14:01:08.262684+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:01:08.266637+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-be05fb81e2 — 2026-09-07 14:02:57.929204+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:02:57.933595+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-1b01fd590a — 2026-09-07 14:03:47.582720+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:03:47.588455+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-deac07be2a — 2026-09-07 14:05:30.178107+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:05:30.180779+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-c5dbd3f4de — 2026-09-07 14:07:51.740113+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-1]: Дра
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-2]: Свой
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-3]: Ну.
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
- User[u-4]: Да.
observations: 0
key events: 4
- #2 PLANNER_DECISION 2026-09-07 14:07:03.871756+00:00 {"intent": "confirm_identity", "turn_id": 2, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-1", "state_version...
- #3 PLANNER_DECISION 2026-09-07 14:07:11.760664+00:00 {"intent": "confirm_identity", "turn_id": 3, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-2", "state_version...
- #4 PLANNER_DECISION 2026-09-07 14:07:17.574250+00:00 {"intent": "confirm_identity", "turn_id": 4, "user_act": "backchannel", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-3", "state_vers...
- #5 CALL_ENDED 2026-09-07 14:07:51.746403+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9aac723ad4 — 2026-09-07 14:10:52.402466+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:10:52.408516+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-22797b6f1e — 2026-09-07 14:12:18.161462+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:12:18.165656+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ffbcac8dc2 — 2026-09-07 14:14:10.130310+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:14:10.134167+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-04c5548d77 — 2026-09-07 14:16:06.822529+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 14:16:06.826655+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b5d126a19c — 2026-09-07 17:11:50.076082+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с Даниил?
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 17:11:50.082104+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-31365dee13 — 2026-09-07 21:08:24.081033+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-1]: Сд.
- Vera: Сейчас не получилось узнать, как у вас дела.
- User[u-2]: Сейчас
observations: 0
key events: 2
- #2 PLANNER_DECISION 2026-09-07 21:08:21.687899+00:00 {"intent": "partial_unresolved_close", "turn_id": 2, "user_act": "question", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "utterance_id": "u-1", "...
- #3 CALL_ENDED 2026-09-07 21:08:21.745068+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-4e3e327b7a — 2026-09-07 21:21:17.038206+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 21:21:17.040618+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-97e9d693a5 — 2026-09-07 21:29:59.230432+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 21:29:59.233280+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b3212ad847 — 2026-09-07 21:31:54.120665+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 21:31:54.125626+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-1b47b87d75 — 2026-09-07 21:51:07.111181+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 21:51:07.115176+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-dad36ca2bf — 2026-09-07 21:52:49.732497+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 21:52:49.740353+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-f0aec9372b — 2026-09-07 22:13:34.303233+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Как вы себя чувствуете?
- Vera: Даниил, мы не смогли выяснить, как вы себя чувствуете.
- Vera: До свидания.
observations: 0
key events: 3
- #2 WAIT_EXPIRED 2026-09-07 22:13:18.802692+00:00 {"turn_id": 2, "wait_id": "wait-66924cc97dfe", "pending_slot": "wellness"}
- #3 WAIT_EXPIRED 2026-09-07 22:13:28.616396+00:00 {"turn_id": 3, "wait_id": "wait-a7bbe2dd8861", "pending_slot": "wellness"}
- #4 CALL_ENDED 2026-09-07 22:13:28.656745+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-55bcd86150 — 2026-09-07 22:38:30.065151+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 22:38:30.069822+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-442a841336 — 2026-09-07 22:38:57.320160+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Как вы себя чувствуете?
- Vera: Даниил, мы не смогли выяснить, как вы себя чувствуете.
- Vera: До свидания.
observations: 0
key events: 3
- #2 WAIT_EXPIRED 2026-09-07 22:38:41.728396+00:00 {"turn_id": 2, "wait_id": "wait-01628829d0ea", "pending_slot": "wellness"}
- #3 WAIT_EXPIRED 2026-09-07 22:38:51.702908+00:00 {"turn_id": 3, "wait_id": "wait-90f55718a3a5", "pending_slot": "wellness"}
- #4 CALL_ENDED 2026-09-07 22:38:51.768287+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-f21993a04f — 2026-09-07 22:45:25.936014+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-1]: Как вы себя чувствуете?
- Vera: Как вы себя чувствуете?
observations: 0
key events: 2
- #2 WAIT_EXPIRED 2026-09-07 22:45:24.535051+00:00 {"turn_id": 2, "wait_id": "wait-b900a59f72af", "pending_slot": "wellness"}
- #3 CALL_ENDED 2026-09-07 22:45:25.938602+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-023339de5e — 2026-09-07 23:14:40.946316+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Как вы себя чувствуете?
- Vera: Даниил, мы не смогли выяснить, как вы себя чувствуете.
- Vera: До свидания.
observations: 0
key events: 3
- #2 WAIT_EXPIRED 2026-09-07 23:14:25.220191+00:00 {"turn_id": 2, "wait_id": "wait-7e285a9a1743", "pending_slot": "wellness"}
- #3 WAIT_EXPIRED 2026-09-07 23:14:34.817976+00:00 {"turn_id": 3, "wait_id": "wait-26fc8af4d8cb", "pending_slot": "wellness"}
- #4 CALL_ENDED 2026-09-07 23:14:34.886063+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-d6a2e17c40 — 2026-09-07 23:17:00.511100+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Как вы себя чувствуете?"}
dialogue:
- User[u-1]: Здравствуйте, это сервис. Как вы себя чувствуете?
- Vera: Как у вас настроение?
- Vera: Как у вас настроение?
- Vera: Как вы себя чувствуете?
- User[u-5]: Здравствуйте.
observations: 1
- t2 [wellness] Как вы себя чувствуете? | quote: Как вы себя чувствуете?
key events: 4
- #2 PLANNER_DECISION 2026-09-07 23:16:39.054701+00:00 {"intent": "check_mood", "turn_id": 2, "user_act": "answer", "fsm_state": "DAILY_CHECK", "pending_slot": "mood", "utterance_id": "u-1", "state_version": 4}
- #3 WAIT_EXPIRED 2026-09-07 23:16:48.348077+00:00 {"turn_id": 3, "wait_id": "wait-affb62f2d10e", "pending_slot": "mood"}
- #4 WAIT_EXPIRED 2026-09-07 23:16:57.858144+00:00 {"turn_id": 4, "wait_id": "wait-256f67048a6f", "pending_slot": "mood"}
- #5 CALL_ENDED 2026-09-07 23:16:57.932013+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-93be0754bc — 2026-09-07 23:40:39.118787+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-1]: Как вы себя чувствуете?
- Vera: Как вы себя чувствуете?
- User[u-2]: Вы себя чувствуете?
- Vera: Даниил, мы не смогли выяснить, как вы себя чувствуете.
- Vera: До свидания.
- User[u-3]: Сюда.
observations: 0
key events: 3
- #2 WAIT_EXPIRED 2026-09-07 23:40:23.284542+00:00 {"turn_id": 2, "wait_id": "wait-075d6a4a7344", "pending_slot": "wellness"}
- #3 WAIT_EXPIRED 2026-09-07 23:40:33.093940+00:00 {"turn_id": 3, "wait_id": "wait-40e50e3c0f22", "pending_slot": "wellness"}
- #4 CALL_ENDED 2026-09-07 23:40:33.166315+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## gate-smoke — 2026-09-07 23:59:36.417740+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-07 20:29:13.692806+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-44dc10cc5d — 2026-09-08 00:01:33.018277+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-08 00:01:33.022125+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-4447e6c637 — 2026-09-08 00:03:40.707662+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-08 00:03:40.711340+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-617ad9e4a0 — 2026-09-08 00:04:21.758892+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-08 00:04:21.761930+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-62899e9c4e — 2026-09-08 00:05:46.105114+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-08 00:05:46.107771+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-d23efc992a — 2026-09-08 00:52:58.869609+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-08 00:52:58.872019+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ab5b721049 — 2026-09-08 01:06:22.640748+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #2 CALL_ENDED 2026-09-08 01:06:22.644218+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-df75c08d — 2026-09-08 12:38:27.514306+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Как вы себя чувствуете?
- Vera: Здравствуйте.
- Vera: Это сервис IMVERA, Даниил.
- Vera: Как вы себя чувствуете?
observations: 0
key events: 3
- #2 WAIT_EXPIRED 2026-09-08 12:38:18.070285+00:00 {"turn_id": 2, "wait_id": "wait-0b16253dc14c", "pending_slot": "wellness"}
- #3 WAIT_EXPIRED 2026-09-08 12:38:26.367413+00:00 {"turn_id": 3, "wait_id": "wait-d3116f041e18", "pending_slot": "wellness"}
- #4 CALL_ENDED 2026-09-08 12:38:26.431108+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-a1f760cf — 2026-09-08 12:52:45.015526+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Как вы себя чувствуете?
- Vera: Здравствуйте.
- Vera: Это сервис IMVERA, Даниил.
- Vera: Как вы себя чувствуете?
observations: 0
key events: 3
- #2 WAIT_EXPIRED 2026-09-08 12:52:35.289473+00:00 {"turn_id": 2, "wait_id": "wait-96e4046607f7", "pending_slot": "wellness"}
- #3 WAIT_EXPIRED 2026-09-08 12:52:43.772287+00:00 {"turn_id": 3, "wait_id": "wait-72d9c0a31028", "pending_slot": "wellness"}
- #4 CALL_ENDED 2026-09-08 12:52:43.841366+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f0daadb9 — 2026-09-08 13:00:59.133337+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо себя чувствую"}
dialogue:
- User[u-1]: Привет. Чувствую себя хорошо.
- Vera: Здравствуйте.
- Vera: Это сервис IMVERA, Даниил.
- Vera: Как вы себя чувствуете?
- User[u-2]: Алло, ты
- Vera: Здравствуйте.
- Vera: Как вы себя чувствуете?
- User[u-3]: Хорошо себя чувствую.
- Vera: Сейчас не получилось узнать, как у вас дела.
- Vera: До свидания.
observations: 2
- t2 [wellness] Чувствую себя хорошо | quote: Привет. Чувствую себя хорошо.
- t4 [wellness] Хорошо себя чувствую | quote: Хорошо себя чувствую.
key events: 4
- #2 PLANNER_DECISION 2026-09-08 13:00:38.285776+00:00 {"intent": "check_mood", "turn_id": 2, "user_act": "question", "fsm_state": "DAILY_CHECK", "pending_slot": "mood", "utterance_id": "u-1", "state_version": 4}
- #3 PLANNER_DECISION 2026-09-08 13:00:45.831305+00:00 {"intent": "check_mood", "turn_id": 3, "user_act": "question", "fsm_state": "DAILY_CHECK", "pending_slot": "mood", "utterance_id": "u-2", "state_version": 6}
- #4 PLANNER_DECISION 2026-09-08 13:00:57.877627+00:00 {"intent": "partial_unresolved_close", "turn_id": 4, "user_act": "answer", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "utterance_id": "u-3", "st...
- #5 CALL_ENDED 2026-09-08 13:00:57.960573+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-14c79443 — 2026-09-08 14:05:36.850174+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Хорошее настроение.", "plans": "А нас нету, в больницу пойду.", "sleep": "спал сегодня", "wellness": "хорошо"}
dialogue:
- User[u-1]: Привет, хорошо.
- Vera: Хорошо. А какое у вас сегодня настроение?
- User[u-2]: Хорошее настроение.
- Vera: Как вы спали?
- User[u-3]: Хорошо спал сегодня.
- Vera: Какие у вас планы на сегодня?
- User[u-4]: А нас нету, в больницу пойду.
- User[u-6]: Что-то непонятно вообще, работает она или нет. Я что-то ей говорю: «Хорошо, хорошо». А по факту вообще работает. И чё-то в какой-то момент просто зависла она и всё, и молчит, ничего не отве
observations: 6
- t3 [wellness] хорошо | quote: хорошо
- t4 [wellness] хорошо | quote: хорошо
- t4 [mood] Хорошее настроение. | quote: Хорошее настроение.
- t5 [wellness] хорошо | quote: хорошо
- t5 [mood] Хорошее настроение. | quote: Хорошее настроение.
- t5 [sleep] спал сегодня | quote: спал сегодня
key events: 1
- #7 CALL_ENDED 2026-09-08 14:05:36.852632+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e9717542 — 2026-09-08 15:09:06.314633+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое", "plans": "Никаких планов нет.", "sleep": "Плохо.", "wellness": "Тебе плохо."}
dialogue:
- User[u-1]: Да
- User[u-2]: Тебе плохо.
- Vera: Хорошо. А какое у вас сегодня настроение?
- User[u-3]: Плохое.
- Vera: Как вы спали?
- User[u-4]: Плохо.
- Vera: Какие у вас планы на сегодня?
- User[u-5]: Никаких планов нет.
observations: 6
- t4 [wellness] Тебе плохо. | quote: Тебе плохо.
- t5 [wellness] Тебе плохо. | quote: Тебе плохо.
- t5 [mood] Плохое | quote: Плохое
- t6 [wellness] Тебе плохо. | quote: Тебе плохо.
- t6 [mood] Плохое | quote: Плохое
- t6 [sleep] Плохо. | quote: Плохо.
key events: 1
- #8 CALL_ENDED 2026-09-08 15:09:06.317456+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1be8664c — 2026-09-08 16:42:34.495249+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-1]: Сам.
observations: 0
key events: 1
- #3 CALL_ENDED 2026-09-08 16:42:34.501082+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1fbe9a6a — 2026-09-08 16:45:52.007757+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое.", "sleep": "Плохо.", "wellness": "Хорошо."}
dialogue:
- User[u-2]: Хорошо.
- Vera: Рада это слышать. А какое у вас сегодня настроение?
- User[u-4]: Плохое.
- Vera: Понимаю. Как вы спали?
- User[u-5]: Плохо.
- Vera: Понимаю, ночь была тяжёлая. Какие у вас планы на сегодня?
observations: 3
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t4 [mood] Плохое. | quote: Плохое.
key events: 1
- #6 CALL_ENDED 2026-09-08 16:45:52.011542+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-28767ff2 — 2026-09-08 18:28:51.249849+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 18:28:26.624628+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 18:28:51.252109+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ab822346 — 2026-09-08 18:28:58.343743+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 18:28:33.732609+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 18:28:58.346563+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-68d06379 — 2026-09-08 18:29:03.849401+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "плохо себя чувствуешь", "sleep": "Плохо.", "wellness": "Хорошо."}
dialogue:
- User[u-1]: Хорошо.
- Vera: Рада это слышать. А какое у вас сегодня настроение?
- User[u-2]: Какое настроение очень?
- Vera: Как у вас настроение — хотя бы коротко?
- User[u-3]: Какое настроение, плохо себя чувствуешь?
- Vera: Понимаю. Как вы спали?
- User[u-4]: Плохо.
- Vera: Понимаю, ночь была тяжёлая. Какие у вас планы на сегодня?
- User[u-5]: На сегодня нету никаких.
observations: 4
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t5 [mood] плохо себя чувствуешь | quote: плохо себя чувствуешь
key events: 1
- #7 CALL_ENDED 2026-09-08 18:29:03.851858+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-6c51dbdd — 2026-09-08 18:49:49.948199+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 18:49:25.375228+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 18:49:49.953903+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-5942df8c — 2026-09-08 18:49:57.139983+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 18:49:32.498469+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 18:49:57.143429+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-c663ec9b — 2026-09-08 20:40:45.314104+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:40:20.920459+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:40:45.321060+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-40b11c29 — 2026-09-08 20:45:43.447101+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:45:18.872857+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:45:43.453154+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-a7077bbc — 2026-09-08 20:50:08.376763+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:49:43.799942+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:50:08.381516+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d35beada — 2026-09-08 20:51:18.160625+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:50:53.515149+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:51:18.163589+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0336ed66 — 2026-09-08 20:53:08.497494+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:52:43.888172+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:53:08.502344+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-68dee177 — 2026-09-08 20:54:27.026444+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:54:02.370176+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:54:27.029918+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-c050c040 — 2026-09-08 20:57:22.123905+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:56:57.560206+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:57:22.126534+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-cf7610ae — 2026-09-08 20:59:25.764454+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:59:01.178798+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 20:59:25.768995+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0cc436e2 — 2026-09-08 21:00:08.164120+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 20:59:43.557343+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:00:08.167859+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f8fe6817 — 2026-09-08 21:00:58.697404+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:00:34.155607+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:00:58.700386+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fb8075a7 — 2026-09-08 21:01:37.504677+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:01:12.889352+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:01:37.508339+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0fbfe4b5 — 2026-09-08 21:02:51.331143+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:02:26.747567+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:02:51.334874+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f1173aac — 2026-09-08 21:04:59.384616+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:04:34.806657+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:04:59.388371+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-7b130bc8 — 2026-09-08 21:06:07.678893+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:05:43.049836+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:06:07.682930+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-b4a924d5 — 2026-09-08 21:07:16.975011+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:06:52.367038+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:07:16.977549+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-86fad0fa — 2026-09-08 21:08:53.136642+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:08:28.550066+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:08:53.143219+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-61e8f675 — 2026-09-08 21:10:10.775065+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:09:46.160059+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:10:10.777649+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-3adf104b — 2026-09-08 21:11:02.014744+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:10:37.413808+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:11:02.017034+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-124baeda — 2026-09-08 21:12:13.832170+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:11:49.182373+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:12:13.835110+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-2d125158 — 2026-09-08 21:13:14.884417+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:12:50.268836+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:13:14.888884+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-09ae279f — 2026-09-08 21:14:19.502465+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:13:54.929405+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:14:19.505560+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f3338b92 — 2026-09-08 21:15:09.410498+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:14:44.782200+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:15:09.413560+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-29b50e8a — 2026-09-08 21:24:18.500055+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое настроение. Говорю, самочувствие плохое.", "sleep": "Плохо.", "wellness": "Хорошо чувствую себя, но состояние не очень."}
dialogue:
- User[u-1]: Хорошо чувствую себя, но состояние не очень.
- Vera: Рада это слышать. А какое у вас сегодня настроение?
- User[u-2]: Плохое настроение. Говорю, самочувствие плохое.
- Vera: Понимаю. Как вы спали?
- User[u-3]: Плохо.
- Vera: Понимаю, ночь была тяжёлая. Какие у вас планы на сегодня?
- Vera: Какие у вас планы на сегодня — в двух словах?
- User[u-4]: Каких планов на сегодня?
observations: 3
- t3 [wellness] Хорошо чувствую себя, но состояние не очень. | quote: Хорошо чувствую себя, но состояние не очень.
- t4 [wellness] Хорошо чувствую себя, но состояние не очень. | quote: Хорошо чувствую себя, но состояние не очень.
- t4 [mood] Плохое настроение. Говорю, самочувствие плохое. | quote: Плохое настроение. Говорю, самочувствие плохое.
key events: 2
- #6 WAIT_EXPIRED 2026-09-08 21:24:04.459760+00:00 {"turn_id": 5, "wait_id": "wait-plans", "pending_slot": "plans"}
- #7 CALL_ENDED 2026-09-08 21:24:18.503693+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-894c4326 — 2026-09-08 21:29:52.345452+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-08 21:29:12.943908+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-08 21:29:52.350609+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-69bd676a — 2026-09-08 21:42:26.276854+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое настроение, говорю.", "plans": "А сидеть дома, ничего не делать.", "sleep": "Плохо.", "wellness": "Я чувствую себя плохо."}
dialogue:
- User[u-1]: Я чувствую себя плохо.
- Vera: Мне жаль это слышать. А какое у вас сегодня настроение?
- User[u-2]: Какое?
- User[u-3]: Плохое настроение, говорю.
- Vera: Понимаю. Как вы спали?
- User[u-4]: Плохо.
- Vera: Понимаю, ночь была тяжёлая. Какие у вас планы на сегодня?
- User[u-5]: А сидеть дома, ничего не делать.
- User[u-6]: Сказано.
- User[u-7]: А нет, это пимба-бомба.
observations: 10
- t3 [wellness] Я чувствую себя плохо. | quote: Я чувствую себя плохо.
- t4 [wellness] Я чувствую себя плохо. | quote: Я чувствую себя плохо.
- t4 [mood] Плохое настроение, говорю. | quote: Плохое настроение, говорю.
- t5 [wellness] Я чувствую себя плохо. | quote: Я чувствую себя плохо.
- t5 [mood] Плохое настроение, говорю. | quote: Плохое настроение, говорю.
- t5 [sleep] Плохо. | quote: Плохо.
- t6 [wellness] Я чувствую себя плохо. | quote: Я чувствую себя плохо.
- t6 [mood] Плохое настроение, говорю. | quote: Плохое настроение, говорю.
- t6 [sleep] Плохо. | quote: Плохо.
- t6 [plans] А сидеть дома, ничего не делать. | quote: А сидеть дома, ничего не делать.
key events: 1
- #9 CALL_ENDED 2026-09-08 21:42:26.282218+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-8054b8c5 — 2026-09-08 22:08:02.399909+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Ну, из-за того, что голова болит, плохое настроение.", "plans": "Планов никаких нету.", "sleep": "Пойдёт, нормально.", "wellness": "Плохо."}
dialogue:
- User[u-1]: Плохо.
- Vera: Что именно беспокоит?
- User[u-2]: Беспокоит головная боль, тошнота.
- Vera: Как давно это продолжается?
- User[u-3]: А, ну, в течение часа, наверное.
- Vera: Мне жаль это слышать. А какое у вас сегодня настроение?
- User[u-4]: Ну, из-за того, что голова болит, плохое настроение.
- Vera: Понимаю. Как вы спали?
- User[u-5]: Пойдёт, нормально.
- Vera: При головной боли лучше не напрягаться. Какие у вас планы на сегодня?
- User[u-6]: Планов никаких нету.
- User[u-7]: Сходить в магазин.
observations: 12
- t3 [wellness] Плохо. | quote: Плохо.
- t4 [wellness] Плохо. | quote: Плохо.
- t5 [wellness] Плохо. | quote: Плохо.
- t6 [wellness] Плохо. | quote: Плохо.
- t6 [mood] Ну, из-за того, что голова болит, плохое настроение. | quote: Ну, из-за того, что голова болит, плохое настроение.
- t7 [wellness] Плохо. | quote: Плохо.
- t7 [mood] Ну, из-за того, что голова болит, плохое настроение. | quote: Ну, из-за того, что голова болит, плохое настроение.
- t7 [sleep] Пойдёт, нормально. | quote: Пойдёт, нормально.
- t8 [wellness] Плохо. | quote: Плохо.
- t8 [mood] Ну, из-за того, что голова болит, плохое настроение. | quote: Ну, из-за того, что голова болит, плохое настроение.
- t8 [sleep] Пойдёт, нормально. | quote: Пойдёт, нормально.
- t8 [plans] Планов никаких нету. | quote: Планов никаких нету.
key events: 1
- #10 CALL_ENDED 2026-09-08 22:08:02.402736+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-3238b70a — 2026-09-08 22:31:26.809534+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Не очень, на самом деле, настроение у меня.", "plans": "Планов нету на сегодня.", "sleep": "Плохо спал. Ну так, хорошо. Спал хорошо.", "wellness": "Чу...
dialogue:
- User[u-1]: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- Vera: Что именно беспокоит?
- User[u-2]: Голова, говорю, болит.
- Vera: Как давно это продолжается?
- User[u-3]: Продолжительное время.
- Vera: Мне жаль это слышать. А какое у вас сегодня настроение?
- User[u-4]: Не очень, на самом деле, настроение у меня.
- Vera: Как вы спали?
- User[u-5]: Плохо спал. Ну так, хорошо. Спал хорошо.
- Vera: Понимаю, ночь была тяжёлая. При головной боли лучше не напрягаться. Какие у вас планы на сегодня?
- User[u-6]: Планов нету на сегодня.
- Vera: Спасибо за разговор.
- User[u-7]: А
observations: 8
- t3 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t4 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t5 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t6 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t6 [mood] Не очень, на самом деле, настроение у меня. | quote: Не очень, на самом деле, настроение у меня.
- t7 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t7 [mood] Не очень, на самом деле, настроение у меня. | quote: Не очень, на самом деле, настроение у меня.
- t7 [sleep] Плохо спал. Ну так, хорошо. Спал хорошо. | quote: Плохо спал. Ну так, хорошо. Спал хорошо.
key events: 1
- #9 CALL_ENDED 2026-09-08 22:31:26.814183+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-34e06dfc — 2026-09-08 22:32:30.830961+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Великолепное настроение.", "wellness": "Чувствую себя хорошо."}
dialogue:
- User[u-2]: Чувствую себя хорошо.
- Vera: Рада это слышать. А какое у вас сегодня настроение?
- User[u-3]: Великолепное настроение.
- Vera: Как вы спали?
- User[u-4]: Хорошо, спал.
- Vera: Как вы спали — коротко, пожалуйста?
- User[u-5]: Да.
- User[u-6]: Спало великолепно.
observations: 7
- t3 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t4 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t4 [mood] Великолепное настроение. | quote: Великолепное настроение.
- t5 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t5 [mood] Великолепное настроение. | quote: Великолепное настроение.
- t6 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t6 [mood] Великолепное настроение. | quote: Великолепное настроение.
key events: 1
- #8 CALL_ENDED 2026-09-08 22:32:30.835531+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-592f4ea0 — 2026-09-08 22:48:16.378444+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно.", "plans": "Сегодня планов нету. Отдыха...
dialogue:
- Vera: Здравствуйте. Это сервис IMVERA, Даниил. Как вы себя чувствуете?
- User[u-2]: Плохо спал.
- Vera: Что именно беспокоит?
- User[u-3]: Проснулся в четыре, потом долго не мог заснуть, а ещё утром живот немного побаливал.
- Vera: Как давно это продолжается?
- User[u-4]: Сейчас живот уже почти не болит, вроде прошло.
- Vera: Мне жаль это слышать. А какое у вас сегодня настроение?
- User[u-5]: Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно.
- Vera: Понимаю. Как вы спали?
- User[u-6]: Спал в целом нормально.
- Vera: С учётом самочувствия, какие у вас планы на сегодня?
- User[u-7]: Сегодня планов нету. Отдыхаю.
- Vera: Спасибо за разговор.
observations: 8
- t3 [wellness] Плохо спал. | quote: Плохо спал.
- t4 [wellness] Плохо спал. | quote: Плохо спал.
- t5 [wellness] Плохо спал. | quote: Плохо спал.
- t6 [wellness] Плохо спал. | quote: Плохо спал.
- t6 [mood] Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно. | quote: Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно.
- t7 [wellness] Плохо спал. | quote: Плохо спал.
- t7 [mood] Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно. | quote: Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно.
- t7 [sleep] Спал в целом нормально. | quote: Спал в целом нормально.
key events: 1
- #9 CALL_ENDED 2026-09-08 22:48:16.381788+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-641ab72d — 2026-09-08 22:56:30.956808+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое.", "wellness": "Чувствую себя плохо."}
dialogue:
- Vera: Здравствуйте. Это сервис IMVERA, Даниил. Как вы себя чувствуете?
- User[u-1]: Чувствую себя плохо.
- Vera: Что именно беспокоит?
- User[u-2]: Сердце болит с самого утра.
- Vera: Как давно это продолжается?
- User[u-3]: Самого утра.
- Vera: Мне жаль это слышать. А какое у вас сегодня настроение?
- User[u-4]: Плохое.
- Vera: Понимаю. Как вы спали?
- User[u-5]: А-а, плохо болело сердце. Я же говорил же.
observations: 5
- t3 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t4 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t5 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t6 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t6 [mood] Плохое. | quote: Плохое.
key events: 1
- #8 CALL_ENDED 2026-09-08 22:56:30.961271+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c33d32e8 — 2026-09-09 00:03:06.978891+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис IMVERA, Даниил. Как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-09 00:02:51.466812+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-09 00:03:06.984983+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d8838b70 — 2026-09-09 00:03:28.901891+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Хорошая.", "plans": "Планов нет на сегодня.", "sleep": "Нормально пойдёт.", "wellness": "Пять."}
dialogue:
- Vera: Здравствуйте. Это сервис IMVERA, Даниил. Как вы себя чувствуете?
- User[u-1]: Пять.
- Vera: Рада это слышать. А какое у вас сегодня настроение?
- User[u-2]: Хорошая.
- Vera: Как вы спали?
- User[u-3]: Нормально пойдёт.
- Vera: Какие у вас планы на сегодня?
- User[u-4]: Планов нет на сегодня.
- Vera: Спасибо за разговор.
observations: 6
- t3 [wellness] Пять. | quote: Пять.
- t4 [wellness] Пять. | quote: Пять.
- t4 [mood] Хорошая. | quote: Хорошая.
- t5 [wellness] Пять. | quote: Пять.
- t5 [mood] Хорошая. | quote: Хорошая.
- t5 [sleep] Нормально пойдёт. | quote: Нормально пойдёт.
key events: 1
- #7 CALL_ENDED 2026-09-09 00:03:28.905945+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f9f41447 — 2026-09-09 00:05:16.123812+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое.", "wellness": "Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела."}
dialogue:
- Vera: Здравствуйте. Это сервис IMVERA, Даниил. Как вы себя чувствуете?
- User[u-2]: Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела.
- Vera: Как давно это продолжается?
- User[u-3]: Уже с четырёх утра.
- Vera: Мне жаль это слышать. А какое у вас сегодня настроение?
- User[u-4]: Плохое.
- Vera: Понимаю. Как вы спали?
observations: 2
- t3 [wellness] Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела. | quote: Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела.
- t4 [wellness] Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела. | quote: Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела.
key events: 1
- #6 CALL_ENDED 2026-09-09 00:05:16.126248+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a80ee60f — 2026-09-09 00:10:14.044071+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "голова болит и тошнит меня"}
dialogue:
- User[u-1]: Так
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- User[u-2]: Ну, состояние не очень, голова болит и тошнит меня.
- Vera: Понимаю. Как давно болит голова?
- User[u-3]: С 10:00 утра, наверное, где-то так.
- Vera: Понимаю. Боль сильная или терпимая?
- User[u-4]: Угу
- User[u-5]: Ну, сильная.
- Vera: Понятно. А сейчас живот ещё беспокоит?
- User[u-6]: Разде говорил живот.
- Vera: Понятно. А сейчас живот ещё беспокоит?
- User[u-7]: Я говорю: «А я живот говорил, что у меня болит».
observations: 2
- t7 [wellness] голова болит и тошнит меня | quote: голова болит и тошнит меня
- t8 [wellness] голова болит и тошнит меня | quote: голова болит и тошнит меня
key events: 1
- #10 CALL_ENDED 2026-09-09 00:10:14.047326+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## pg-a33099787e40 — 2026-09-09 01:35:13.819081+00:00 (fsm=DAILY_CHECK, termination=None)

family=fam-pg-test ended=False
facts={}
observations: 0
key events: 2
- #2 PLANNER_DECISION 2026-09-09 01:35:13.785107+00:00 {"intent": "wait_for_continuation", "turn_id": 2, "user_act": "backchannel", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utt...
- #3 PLANNER_DECISION 2026-09-09 01:35:13.804006+00:00 {"intent": "check_wellness", "turn_id": 3, "user_act": "answer", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id": ...

## pg-idem-989baebc34f8 — 2026-09-09 01:35:13.930337+00:00 (fsm=DAILY_CHECK, termination=None)

family=fam-pg-idem ended=False
facts={}
observations: 0
key events: 4
- #2 PLANNER_DECISION 2026-09-09 01:35:13.865772+00:00 {"intent": "wait_for_continuation", "turn_id": 2, "user_act": "backchannel", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utt...
- #3 PLANNER_DECISION 2026-09-09 01:35:13.881665+00:00 {"intent": "check_wellness", "turn_id": 3, "user_act": "answer", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id": ...
- #4 PLANNER_DECISION 2026-09-09 01:35:13.898452+00:00 {"intent": "check_wellness", "turn_id": 4, "user_act": "unclear", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id":...
- #5 PLANNER_DECISION 2026-09-09 01:35:13.916276+00:00 {"intent": "repair_repeat", "turn_id": 5, "user_act": "repeat", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id": "...

## pg-3778ef2f9083 — 2026-09-09 01:35:18.592443+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-test ended=True
facts={}
observations: 0
key events: 3
- #2 PLANNER_DECISION 2026-09-09 01:35:18.535590+00:00 {"intent": "confirm_consent", "turn_id": 2, "user_act": "answer", "fsm_state": "CHECK_CONSENT", "pending_slot": null, "skip_planner": false, "utterance_id": "u-...
- #3 PLANNER_DECISION 2026-09-09 01:35:18.557403+00:00 {"intent": "consent_declined_final", "turn_id": 3, "user_act": "answer", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "skip_planner": false, "utte...
- #4 CALL_ENDED 2026-09-09 01:35:18.597014+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## pg-idem-209887c7bf16 — 2026-09-09 01:35:18.684535+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-idem ended=True
facts={}
observations: 0
key events: 3
- #2 PLANNER_DECISION 2026-09-09 01:35:18.640682+00:00 {"intent": "confirm_consent", "turn_id": 2, "user_act": "answer", "fsm_state": "CHECK_CONSENT", "pending_slot": null, "skip_planner": false, "utterance_id": "u-...
- #3 PLANNER_DECISION 2026-09-09 01:35:18.656130+00:00 {"intent": "consent_declined_final", "turn_id": 3, "user_act": "answer", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "skip_planner": false, "utte...
- #4 CALL_ENDED 2026-09-09 01:35:18.686663+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## fs-72b01e3c — 2026-09-09 02:07:09.961455+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-1]: Привет. Чувствую себя сейчас в данный момент хорошо. В 4:00 утра болела у меня голова и в 3:00 болело у меня колено.
observations: 0
key events: 1
- #3 CALL_ENDED 2026-09-09 02:07:09.966014+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e3e257e1 — 2026-09-09 02:38:25.708505+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Хуёвое у меня настроение, вера, хуёвое.", "wellness": "Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю."}
dialogue:
- User[u-1]: Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю.
- Vera: Как давно это продолжается?
- User[u-2]: Это продолжается уже пятый час, твою мать!
- Vera: Мне жаль это слышать. А какое у вас сегодня настроение?
- User[u-3]: Хуёвое у меня настроение, вера, хуёвое.
- Vera: Как вы спали?
- User[u-4]: Отвратительный верс Пал. Что за вопросы дурацкие?
- Vera: Я Вера, голосовой помощник IMVERA. Звоню, чтобы узнать, как вы себя чувствуете.
- User[u-5]: Пиво себя чувствую. Вера, умираю.
- Vera: Понимаю. Как вы спали — коротко, пожалуйста?
- User[u-6]: Я же говорил, что плохо спал.
- Vera: Да, вы говорили, что плохой сон. Как давно плохой сон?
- User[u-7]: Сегодня как?
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 10
- t3 [wellness] Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю. | quote: Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю.
- t4 [wellness] Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю. | quote: Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю.
- t5 [wellness] Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю. | quote: Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю.
- t5 [mood] Хуёвое у меня настроение, вера, хуёвое. | quote: Хуёвое у меня настроение, вера, хуёвое.
- t6 [wellness] Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю. | quote: Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю.
- t6 [mood] Хуёвое у меня настроение, вера, хуёвое. | quote: Хуёвое у меня настроение, вера, хуёвое.
- t7 [wellness] Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю. | quote: Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю.
- t7 [mood] Хуёвое у меня настроение, вера, хуёвое. | quote: Хуёвое у меня настроение, вера, хуёвое.
- t8 [wellness] Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю. | quote: Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю.
- t8 [mood] Хуёвое у меня настроение, вера, хуёвое. | quote: Хуёвое у меня настроение, вера, хуёвое.
key events: 1
- #10 CALL_ENDED 2026-09-09 02:38:25.711613+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ad907a00 — 2026-09-09 19:37:57.704656+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-2]: А чувствую себя отвратительно, болит голова и очень тошнит меня.
- Vera: Понимаю, голова болит. Как давно болит голова?
- User[u-3]: Но
- Vera: Боль сильная или терпимая?
- User[u-4]: Боль достаточно боль достаточно сильная, но ещё меня тошнит.
- Vera: Понимаю, Боль. Как давно Боль?
- User[u-5]: Боль четыре часа.
- Vera: Понимаю, Боль. Как давно Боль?
- User[u-6]: Четыре часа.
- Vera: Как давно тошнит?
- User[u-7]: Уже давно тошнит.
- User[u-8]: Давно, давно тошнит.
- User[u-9]: Блядь.
- Vera: Боль сильная или терпимая?
- User[u-10]: Боль достаточно терпимая.
- User[u-11]: Боль терпимая, Вера.
- User[u-12]: Тут по факту и есть мой сервис.
- Vera: Как давно тошнит?
- User[u-13]: Тошнит.
- User[u-14]: Не понимаю просто, чего она так долго отвечает.
- User[u-15]: Бляджи.
observations: 0
key events: 1
- #12 CALL_ENDED 2026-09-09 19:37:57.711267+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-78aadac2 — 2026-09-09 20:09:30.658154+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-1]: Четыреста
- Vera: Понимаю. Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- User[u-2]: Смотри.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-09 20:09:30.661834+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-77afbbf1 — 2026-09-09 20:10:10.381892+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
dialogue:
- User[u-1]: Привет, чувствую себя не очень. Голова болит, чё-то плохо чувствую себя.
- Vera: Как давно это продолжается?
- User[u-2]: Достаточно давно.
- Vera: Как давно болит голова?
- User[u-3]: Голова болит уже давно.
observations: 1
- t3 [wellness] negative | quote: negative
key events: 1
- #5 CALL_ENDED 2026-09-09 20:10:10.384214+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-9032fcf4 — 2026-09-09 22:02:37.914340+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
dialogue:
- User[u-1]: Чувствую себя плохо, голова болит и тошнит меня.
- Vera: Как давно это продолжается?
- User[u-2]: Вчерашнего дня
- Vera: Я уточняю про сейчас: голова болит ещё беспокоит или уже прошло?
- User[u-3]: А уже прошла.
- Vera: Боль сильная или терпимая?
- User[u-4]: Боль отсутствует. Голова, говорю, прошла.
- Vera: Понимаю, голова боль. Боль сильная или терпимая?
observations: 3
- t3 [wellness] negative | quote: negative
- t4 [wellness] negative | quote: negative
- t5 [wellness] negative | quote: negative
key events: 1
- #7 CALL_ENDED 2026-09-09 22:02:37.919479+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-996c3fa1 — 2026-09-10 11:40:02.918657+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- User[u-2]: Хорошо, настроение нормальное, всё хорошо.
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-10 11:40:02.921445+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c83012aa — 2026-09-10 12:08:59.381357+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "positive"}
dialogue:
- User[u-2]: Настроение вроде бы тоже нормальное.
- Vera: Спасибо за разговор.
- User[u-3]: Всё, что ли?
- Vera: Спасибо за разговор.
observations: 1
- t3 [mood] positive | quote: positive
key events: 1
- #5 CALL_ENDED 2026-09-10 12:08:59.383543+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f534c2e6 — 2026-09-10 12:22:44.249398+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "positive", "wellness": "positive"}
dialogue:
- User[u-2]: Привет! Чувствую себя хорошо, настроение хорошее?
- Vera: Есть ли ещё что-то важное, чем вы хотели бы поделиться?
- User[u-3]: Да вроде бы нет, планов толком тоже нет никаких. Так вроде всё нормально.
- Vera: Понимаю. Расскажите, пожалуйста, коротко.
- User[u-4]: Я ж сказал уже всё.
- Vera: Спасибо за разговор.
observations: 4
- t3 [wellness] positive | quote: positive
- t3 [mood] positive | quote: positive
- t4 [wellness] positive | quote: positive
- t4 [mood] positive | quote: positive
key events: 1
- #6 CALL_ENDED 2026-09-10 12:22:44.251391+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-587e6306 — 2026-09-10 12:37:47.398893+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #3 CALL_ENDED 2026-09-10 12:37:47.401561+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0fc0055e — 2026-09-10 12:44:25.192048+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #3 CALL_ENDED 2026-09-10 12:44:25.194277+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0c4eb96b — 2026-09-10 12:45:25.462911+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #3 CALL_ENDED 2026-09-10 12:45:25.464909+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1f6d3000 — 2026-09-10 12:52:12.574254+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
dialogue:
- User[u-1]: Привет. Чувствую себя вроде бы хорошо, но состояние такое плохое.
- Vera: Как давно это продолжается?
- User[u-2]: Ну, наверное, со вчерашнего дня плохое самочувствие, вот головная боль.
- Vera: Спасибо за разговор. Хотите ещё что-то добавить?
- User[u-3]: Не спросишь там, ещё что-то.
- Vera: Хорошо, записала. Всё, спасибо, Даниил. Всего вам хорошего. До свидания.
- User[u-4]: До свидания.
- Vera: Вы хотите закончить разговор?
- User[u-5]: Да.
- Vera: Всё, спасибо, Даниил. Всего вам хорошего. До свидания.
observations: 4
- t3 [wellness] negative | quote: negative
- t4 [wellness] negative | quote: negative
- t5 [wellness] negative | quote: negative
- t6 [wellness] negative | quote: negative
key events: 1
- #8 CALL_ENDED 2026-09-10 12:52:12.576702+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-69673837 — 2026-09-10 15:38:50.162341+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "positive"}
dialogue:
- User[u-1]: Да.
- Vera: Спасибо за разговор. Хотите ещё что-то добавить?
- User[u-2]: Да вроде нормально всё.
- Vera: Хорошо, записала. Всё, спасибо, Даниил. Всего вам хорошего. До свидания.
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-10 15:38:50.168219+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-2b372628 — 2026-09-10 15:39:56.625423+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено болит."}
dialogue:
- User[u-1]: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено болит.
- Vera: Понимаю, болит. Когда началась головная боль и сейчас ещё беспокоит или уже стало лучше?
- User[u-2]: Угу
- User[u-3]: Головная боль сейчас прошла, но болит колено. Я же говорю, колено болит ещё.
- Vera: Как давно колено болит?
- User[u-4]: Колено болит вот со вчерашнего дня.
- Vera: Спасибо за разговор. Хотите ещё что-то добавить?
- User[u-5]: Хмм, да, хотел бы, также хотел бы передать родственникам, что у меня так всё нормально, всё в порядке. Жива-здорова.
- Vera: Хорошо, записала. Всё, спасибо, Даниил. Всего вам хорошего. До свидания.
- User[u-6]: Да.
- Vera: Всё, спасибо, Даниил. Всего вам хорошего. До свидания.
observations: 5
- t3 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t4 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t5 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t6 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t7 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
key events: 1
- #9 CALL_ENDED 2026-09-10 15:39:56.630904+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c49395f7 — 2026-09-11 00:44:29.230265+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит."}
dialogue:
- User[u-1]: Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит.
- Vera: Понимаю, болит. Когда началась головная боль и сейчас ещё беспокоит или уже стало лучше?
- User[u-3]: Смотри, а-а помимо головной боли, что я тебе ещё сказал, что у меня болит?
- Vera: Понимаю, боли. Как давно болит голова?
- User[u-4]: Я тебе говорю, что если ещё скажешь, что у меня болит?
- Vera: Понимаю, болит. Как давно это продолжается?
observations: 2
- t3 [wellness] Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит. | quote: Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит.
- t4 [wellness] Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит. | quote: Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит.
key events: 1
- #6 CALL_ENDED 2026-09-11 00:44:29.238940+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## call-pgproof01 — 2026-09-11 16:12:13.024700+00:00 (fsm=CALL_START, termination=None)

family=fam-pg-proof ended=False
facts={}
observations: 0
key events: 0

## call-pgproof02 — 2026-09-11 16:12:38.107158+00:00 (fsm=CALL_START, termination=None)

family=fam-pg-proof ended=False
facts={}
observations: 0
key events: 0

## call-pgproof03 — 2026-09-11 16:12:56.702816+00:00 (fsm=CALL_START, termination=None)

family=fam-pg-proof ended=False
facts={}
observations: 0
key events: 0

## call-bed4283a7fb0 — 2026-09-11 16:20:13.268709+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## call-e19535814d4f — 2026-09-11 16:21:28.651835+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## call-9a9826374760 — 2026-09-11 16:23:19.003232+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## call-live-final1 — 2026-09-11 16:24:10.005621+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## pg-bind-4b85dc9110b6 — 2026-09-11 16:24:31.986736+00:00 (fsm=CALL_START, termination=None)

family=fam-pg-bind ended=False
facts={}
observations: 0
key events: 0

## fs-167f0832 — 2026-09-11 17:30:19.410869+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, Как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-11 17:30:18.926453+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-11 17:30:19.414375+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## call-649ce7f66929 — 2026-09-11 17:32:08.895681+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## call-f958b19123da — 2026-09-11 17:32:54.956099+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## fs-aef2ccee — 2026-09-11 17:33:57.790901+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, Как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-11 17:33:57.672531+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #5 CALL_ENDED 2026-09-11 17:33:57.794182+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## call-19e219e2b1e8 — 2026-09-11 17:35:24.734437+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## fs-bf61f52b — 2026-09-11 19:38:31.030485+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Да"}
dialogue:
- User[u-1]: Да
- Vera: Спасибо за разговор. Хотите ещё что-то добавить?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-11 19:38:31.035686+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-223c5ba1 — 2026-09-11 21:14:45.227559+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-11 21:14:29.351942+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-11 21:14:45.231655+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fab680cb — 2026-09-11 21:15:42.922162+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя... Ну, сам себя чувствую хорошо. До этого болела у меня голова, и было тошното, плохое самочувствие."}
dialogue:
- User[u-1]: Привет. Чувствую себя... Ну, сам себя чувствую хорошо. До этого болела у меня голова, и было тошното, плохое самочувствие.
- Vera: Понимаю, болела. Как давно болит голова?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-11 21:15:42.925246+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-2ba16ccd — 2026-09-11 21:18:11.404647+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-11 21:18:11.410218+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1839074e — 2026-09-11 21:18:11.959264+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо."}
dialogue:
- User[u-1]: Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо.
- Vera: Понимаю, болела. А сейчас голова ещё болит или уже почти прошла?
- User[u-2]: Голова почти прошла.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-3]: Смотри, Вера, у меня ещё тошнит меня очень жёстко. Прям вообще ужас.
- Vera: Понимаю, тошнит. Как давно тошнит?
- User[u-4]: Шли достаточно долго уже, уже четыре раза вырвало меня.
- Vera: Я вас слушаю. Как давно тошнит?
observations: 3
- t3 [wellness] Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо. | quote: Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо.
- t4 [wellness] Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо. | quote: Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо.
- t5 [wellness] Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо. | quote: Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо.
key events: 1
- #8 CALL_ENDED 2026-09-11 21:18:11.962428+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-8489e41a — 2026-09-11 22:55:40.637045+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-11 22:55:25.180758+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-11 22:55:40.640742+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-801bd4fc — 2026-09-11 22:57:07.212699+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-11 22:56:51.766245+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-11 22:57:07.215200+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-9621515c — 2026-09-11 23:00:44.013626+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё.
- Vera: Поняла вас. Головная боль и тошнота — это неприятно, давайте уточним по порядку. Когда начала болеть голова — сегодня или раньше?
- User[u-2]: Начала болеть сегодня, но в данный момент уже она прошла.
- Vera: С этой проблемой вы можете пока справиться сами или вам сейчас нужна помощь близких?
- User[u-3]: Могу справиться самостоятельно, конечно.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-4]: Нет, всё, больше ничего нет. Так всё хорошо у меня.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили головная боль, тошнота и боль. На сегодня всё. Берегите себя. До свидания.
observations: 3
- t3 [wellness] Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё. | quote: Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё.
- t4 [wellness] Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё. | quote: Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё.
- t5 [wellness] Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё. | quote: Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё.
key events: 1
- #8 CALL_ENDED 2026-09-11 23:00:44.017310+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-4b1c368e — 2026-09-12 01:22:49.344832+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-12 01:22:49.348972+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-213aae70 — 2026-09-12 01:23:55.042264+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Привет, чувствую себя очень плохо, болит голова и меня тошнит."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет, чувствую себя очень плохо, болит голова и меня тошнит.
- Vera: Поняла вас. Головная боль и тошнота — это неприятно, давайте уточним по порядку. Когда начала болеть голова — сегодня или раньше?
- User[u-2]: Болеть болеть начала голова сегодня, но в данный момент прошло. С тошнотой такжело, сейчас уже всё нормально стало.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-3]: Сейчас хорошо на данный момент, э-э, ни на что не надо обращать внимания. Родным, можешь передать, что со мной всё в порядке, я жива-здорова.
- Vera: Хорошо, записала. Спасибо, Даниил. Я записала: сегодня беспокоили головная боль и тошнота. На сегодня всё. Берегите себя. До свидания.
observations: 2
- t3 [wellness] Привет, чувствую себя очень плохо, болит голова и меня тошнит. | quote: Привет, чувствую себя очень плохо, болит голова и меня тошнит.
- t4 [wellness] Привет, чувствую себя очень плохо, болит голова и меня тошнит. | quote: Привет, чувствую себя очень плохо, болит голова и меня тошнит.
key events: 1
- #7 CALL_ENDED 2026-09-12 01:23:55.046527+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-5b507969 — 2026-09-12 01:28:04.927280+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Нет, отстань."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- User[u-1]: Нет, отстань.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: Нет, нет.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-3]: Лучше
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
- User[u-4]: Понятно пока.
- User[u-5]: Ура.
observations: 3
- t4 [wellness] Нет, отстань. | quote: Нет, отстань.
- t5 [wellness] Нет, отстань. | quote: Нет, отстань.
- t6 [wellness] Нет, отстань. | quote: Нет, отстань.
key events: 2
- #3 WAIT_EXPIRED 2026-09-12 01:27:36.542951+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #9 CALL_ENDED 2026-09-12 01:28:04.928900+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-1d991b27 — 2026-09-12 01:34:32.377800+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет. Чувствую себя хорошо.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-12 01:34:32.379672+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f3b28dd3 — 2026-09-12 01:36:26.613000+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Уже по-другому говорит. Чувствуй себя хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Уже по-другому говорит. Чувствуй себя хорошо.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: Нет, обращать внимания ни на что не нужно. Всё, спасибо большое, пока.
- Vera: Поняла вас. Большое — зафиксировала. С этой проблемой вы можете пока справиться сами или вам сейчас нужна помощь близких?
- User[u-3]: Никакой помощи не надо, — говорю. Всё хорошо. Пока, — говорю.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили большое. На сегодня всё. Берегите себя. До свидания.
observations: 2
- t3 [wellness] Уже по-другому говорит. Чувствуй себя хорошо. | quote: Уже по-другому говорит. Чувствуй себя хорошо.
- t4 [wellness] Уже по-другому говорит. Чувствуй себя хорошо. | quote: Уже по-другому говорит. Чувствуй себя хорошо.
key events: 1
- #7 CALL_ENDED 2026-09-12 01:36:26.615857+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-965f5b0b — 2026-09-12 01:42:10.943602+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-12 01:42:10.946036+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-54c67d76 — 2026-09-13 14:14:23.686505+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Почему она говорит Даниил? Откуда?
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-13 14:14:23.690380+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-87312170 — 2026-09-13 14:15:10.367933+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: Живот болит после того, как покушал.
- Vera: Поняла вас. Живот болит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-3]: Колю покушал когда?
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-4]: Поднял.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 3
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
key events: 1
- #8 CALL_ENDED 2026-09-13 14:15:10.370076+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-c436546b — 2026-09-13 14:19:05.862136+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: Живот болит.
- Vera: Поняла вас. Живот болит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-3]: Началось, когда покушал.
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-4]: Началось, когда покушал.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
- User[u-5]: Меняет.
observations: 4
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
key events: 1
- #9 CALL_ENDED 2026-09-13 14:19:05.864196+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d42264b9 — 2026-09-13 14:34:37.643263+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: Живот болит.
- Vera: Поняла вас. Живот болит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-3]: Вот когда утром макароны поел.
- Vera: А живот сейчас ещё беспокоит или уже стало лучше?
- User[u-4]: Болит чуток.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили боль в животе. На сегодня всё. Берегите себя. До свидания.
- User[u-5]: Ну блядь, всё равно типа
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили боль в животе. На сегодня всё. Берегите себя. До свидания.
observations: 4
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
key events: 1
- #9 CALL_ENDED 2026-09-13 14:34:37.645558+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a7bffaf1 — 2026-09-13 14:37:57.860539+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
- Vera: Поняла вас. Головная боль и тошнота — это неприятно, давайте уточним по порядку. Когда начала болеть голова — сегодня или раньше?
- User[u-2]: Головная боль начала болеть с 6:00 утра до 8 вечера.
- Vera: Поняла вас. Голова боль — зафиксировала. Боль сильная или терпимая?
- User[u-3]: Боль была достаточно сильной, но она прошла.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-4]: Таблетку забыла выпить от сосудов.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-5]: Таблетку было выпить от давления.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 4
- t3 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
- t4 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
- t5 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
- t6 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
key events: 1
- #9 CALL_ENDED 2026-09-13 14:37:57.863438+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-41e2a57b — 2026-09-13 14:38:54.466692+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Пло."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Пло.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: Сердце болит, я падаю, мне плохо, теряю сознание.
- Vera: Поняла вас. Сердце болит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-3]: Сейчас, я же говорю, я сейчас умру, я задыхаюсь уже.
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-4]: Сейчас я умираю, блядь.
- Vera: Как вы себя чувствуете?
- User[u-5]: Спали того.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 4
- t3 [wellness] Пло. | quote: Пло.
- t4 [wellness] Пло. | quote: Пло.
- t5 [wellness] Пло. | quote: Пло.
- t6 [wellness] Пло. | quote: Пло.
key events: 1
- #9 CALL_ENDED 2026-09-13 14:38:54.468657+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0843128c — 2026-09-13 14:51:48.810701+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "negative", "plans": "У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплять в глаза...
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Плохо.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплять в глаза лекарство. Забыла собаку выгулить. Забыла продукты купить в
- Vera: Поняла вас. Голова болит — зафиксировала. Боль сильная или терпимая?
- User[u-3]: Люпимая.
- Vera: Я вас слушаю. Боль сильная или терпимая?
- User[u-4]: Терпимая.
- Vera: Хорошо. Про сердце болит — когда это началось — сегодня или раньше?
- User[u-5]: Сейчас сердце болит.
- Vera: Хорошо. Про болят — когда это началось — сегодня или раньше?
- User[u-6]: Про что ты?
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-7]: Ноги.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 17
- t3 [wellness] Плохо. | quote: Плохо.
- t3 [mood] negative | quote: negative
- t4 [wellness] Плохо. | quote: Плохо.
- t4 [mood] negative | quote: negative
- t4 [plans] У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят | quote: У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят
- t5 [wellness] Плохо. | quote: Плохо.
- t5 [mood] negative | quote: negative
- t5 [plans] У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят | quote: У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят
- t6 [wellness] Плохо. | quote: Плохо.
- t6 [mood] negative | quote: negative
- t6 [plans] У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят | quote: У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят
- t7 [wellness] Плохо. | quote: Плохо.
- t7 [mood] negative | quote: negative
- t7 [plans] У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят | quote: У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят
- t8 [wellness] Плохо. | quote: Плохо.
- t8 [mood] negative | quote: negative
- t8 [plans] У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят | quote: У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплят
key events: 1
- #11 CALL_ENDED 2026-09-13 14:51:48.812494+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-a8964347 — 2026-09-13 15:05:01.971058+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Я чувствую себя плохо, болит живот и головная боль в данный момент."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Я чувствую себя плохо, болит живот и головная боль в данный момент.
- Vera: Поняла вас. Головная боль и боль в животе — это неприятно, давайте уточним по порядку. Когда это началось — сегодня или раньше?
- User[u-2]: Началось это буквально 3 ч назад.
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-3]: Уже началось.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 2
- t3 [wellness] Я чувствую себя плохо, болит живот и головная боль в данный момент. | quote: Я чувствую себя плохо, болит живот и головная боль в данный момент.
- t4 [wellness] Я чувствую себя плохо, болит живот и головная боль в данный момент. | quote: Я чувствую себя плохо, болит живот и головная боль в данный момент.
key events: 1
- #7 CALL_ENDED 2026-09-13 15:05:01.973219+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0a6c52eb — 2026-09-13 23:28:36.646703+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-13 23:28:36.648937+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-16d22975 — 2026-09-13 23:30:04.486519+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Триво.", "sleep": "Нет.", "wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: Вы сегодня приняли лекарство, которое обычно должны принять?
- User[u-2]: Не приняла.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-3]: Нет.
- Vera: А настроение сегодня как — ничего не тревожит?
- User[u-4]: Триво.
- Vera: А спалось сегодня нормально?
- User[u-5]: Нет.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-6]: Есть.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-7]: Наз болит.
- Vera: Поняла вас. Болит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-8]: Дальше.
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-9]: Раньше началось это.
- Vera: Как вы себя чувствуете?
- User[u-10]: Плохо.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 20
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
- t6 [mood] Триво. | quote: Триво.
- t7 [wellness] Хорошо. | quote: Хорошо.
- t7 [mood] Триво. | quote: Триво.
- t7 [sleep] Нет. | quote: Нет.
- t8 [wellness] Хорошо. | quote: Хорошо.
- t8 [mood] Триво. | quote: Триво.
- t8 [sleep] Нет. | quote: Нет.
- t9 [wellness] Хорошо. | quote: Хорошо.
- t9 [mood] Триво. | quote: Триво.
- t9 [sleep] Нет. | quote: Нет.
- t10 [wellness] Хорошо. | quote: Хорошо.
- t10 [mood] Триво. | quote: Триво.
- t10 [sleep] Нет. | quote: Нет.
- t11 [wellness] Хорошо. | quote: Хорошо.
- t11 [mood] Триво. | quote: Триво.
- t11 [sleep] Нет. | quote: Нет.
key events: 1
- #14 CALL_ENDED 2026-09-13 23:30:04.490070+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-07ba9ace — 2026-09-13 23:41:56.385565+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: Скажите, а лекарства вы каждый день принимаете?
- User[u-2]: Не каждый день.
- Vera: А сегодня принять не забыли?
- User[u-3]: Был.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-4]: Кушал.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-5]: Но вот у кого поглушил чуть живот прибавил.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-6]: Покушал, живот приболел.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 5
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
- t7 [wellness] Хорошо. | quote: Хорошо.
key events: 1
- #10 CALL_ENDED 2026-09-13 23:41:56.387843+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-07799215 — 2026-09-13 23:43:21.175729+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Настроение плохое беспокоит, что у меня голова болит.", "plans": "Пойдёт.", "wellness": "Чувствую себя хорошо. Ты, блядь, подвизы её."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Чувствую себя хорошо. Ты, блядь, подвизы её.
- Vera: А таблетки вам каждый день назначены?
- User[u-2]: Нет. Чего она несёт, блин?
- Vera: А покушать сегодня уже успели?
- User[u-3]: Нет.
- Vera: Как настроение? Ничего не беспокоит?
- User[u-4]: Настроение плохое беспокоит, что у меня голова болит.
- Vera: Поняла вас. Беспокоит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-5]: На восемь.
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-6]: Вчера в 8:00
- Vera: Хорошо. Когда начала болеть голова — сегодня или раньше?
- User[u-7]: В 8:00 начала болеть голова.
- Vera: Поняла вас. Голова болеть — зафиксировала. Боль сильная или терпимая?
- User[u-8]: Пойдёт.
- Vera: Боль сильная или терпимая?
- User[u-9]: Пойдёт.
- Vera: Как вы себя чувствуете?
- User[u-10]: Чувствую себя плохо.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 17
- t3 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t4 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t5 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t6 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t6 [mood] Настроение плохое беспокоит, что у меня голова болит. | quote: Настроение плохое беспокоит, что у меня голова болит.
- t7 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t7 [mood] Настроение плохое беспокоит, что у меня голова болит. | quote: Настроение плохое беспокоит, что у меня голова болит.
- t8 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t8 [mood] Настроение плохое беспокоит, что у меня голова болит. | quote: Настроение плохое беспокоит, что у меня голова болит.
- t9 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t9 [mood] Настроение плохое беспокоит, что у меня голова болит. | quote: Настроение плохое беспокоит, что у меня голова болит.
- t10 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t10 [mood] Настроение плохое беспокоит, что у меня голова болит. | quote: Настроение плохое беспокоит, что у меня голова болит.
- t10 [plans] Пойдёт. | quote: Пойдёт.
- t11 [wellness] Чувствую себя хорошо. Ты, блядь, подвизы её. | quote: Чувствую себя хорошо. Ты, блядь, подвизы её.
- t11 [mood] Настроение плохое беспокоит, что у меня голова болит. | quote: Настроение плохое беспокоит, что у меня голова болит.
- t11 [plans] Пойдёт. | quote: Пойдёт.
key events: 1
- #14 CALL_ENDED 2026-09-13 23:43:21.178234+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fe48f985 — 2026-09-13 23:57:20.736441+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело.", "wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: Скажите, а лекарства вы каждый день принимаете?
- User[u-2]: Каждый день.
- Vera: А сегодня принять не забыли?
- User[u-3]: Сегодня выпило.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-4]: Покушала.
- Vera: А настроение сегодня как — ничего не тревожит?
- User[u-5]: Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело.
- Vera: Поняла вас. Горло приболело — зафиксировала. Сегодня удалось хоть немного поесть и попить?
- User[u-7]: Да, удалось.
- Vera: Если поесть не получается — из-за аппетита или другой причины?
- User[u-8]: Горло болит, тяжело кушать тяжёлый дуб. Может, супчик себе сваргать.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-9]: Да нормально, горло пополоскаю, да спать потом лягу в обед. Потом вечером проснусь, э-э ребёнка с садика заберу, домой приду.
- Vera: Хорошо, записала. Спасибо, Даниил. Я записала: сегодня беспокоили горло приболело. На сегодня всё. Берегите себя. До свидания.
observations: 10
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
- t7 [wellness] Хорошо. | quote: Хорошо.
- t7 [mood] Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело. | quote: Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело.
- t8 [wellness] Хорошо. | quote: Хорошо.
- t8 [mood] Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело. | quote: Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело.
- t9 [wellness] Хорошо. | quote: Хорошо.
- t9 [mood] Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело. | quote: Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело.
key events: 1
- #12 CALL_ENDED 2026-09-13 23:57:20.739054+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-ec54e568 — 2026-09-14 00:00:56.500778+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "positive", "sleep": "Спал отлично.", "wellness": "Отлично."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Отлично.
- Vera: Скажите, а лекарства вы каждый день принимаете?
- User[u-2]: Каждый день.
- Vera: А сегодня уже приняли?
- User[u-3]: Да, принял.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-4]: Я покушал и попил.
- Vera: А спалось сегодня нормально?
- User[u-5]: Спал отлично.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-6]: Нет, хорошо.
- Vera: Хорошо, записала. Спасибо, Даниил. На сегодня всё. Берегите себя. До свидания.
observations: 11
- t3 [wellness] Отлично. | quote: Отлично.
- t3 [mood] positive | quote: positive
- t4 [wellness] Отлично. | quote: Отлично.
- t4 [mood] positive | quote: positive
- t5 [wellness] Отлично. | quote: Отлично.
- t5 [mood] positive | quote: positive
- t6 [wellness] Отлично. | quote: Отлично.
- t6 [mood] positive | quote: positive
- t7 [wellness] Отлично. | quote: Отлично.
- t7 [mood] positive | quote: positive
- t7 [sleep] Спал отлично. | quote: Спал отлично.
key events: 1
- #10 CALL_ENDED 2026-09-14 00:00:56.503959+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-5324e8b6 — 2026-09-14 00:01:34.323922+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "negative", "wellness": "Плохо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Плохо.
- Vera: А таблетки вам каждый день назначены?
- User[u-2]: Поэтому
- Vera: А покушать сегодня уже успели?
- User[u-3]: Со мной замуж.
- Vera: А ночью как спали — выспались?
observations: 4
- t3 [wellness] Плохо. | quote: Плохо.
- t3 [mood] negative | quote: negative
- t4 [wellness] Плохо. | quote: Плохо.
- t4 [mood] negative | quote: negative
key events: 1
- #7 CALL_ENDED 2026-09-14 00:01:34.326225+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-4579ea0d — 2026-09-14 00:02:44.159116+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Хорошо. Ой, блядь."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо. Ой, блядь.
- Vera: Скажите, а лекарства вы каждый день принимаете?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-14 00:02:44.160803+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-b1e84021 — 2026-09-14 00:03:34.012886+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Классно."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Классно.
- Vera: А таблетки вам каждый день назначены?
- User[u-2]: Так каждый день.
- Vera: А сегодня принять не забыли?
- User[u-3]: Забыл. Забыл.
- Vera: А покушать сегодня уже успели?
- User[u-4]: Нет, нет.
- Vera: Как настроение? Ничего не беспокоит?
- User[u-5]: Сердце болит, сейчас умру.
- Vera: Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.
observations: 4
- t3 [wellness] Классно. | quote: Классно.
- t4 [wellness] Классно. | quote: Классно.
- t5 [wellness] Классно. | quote: Классно.
- t6 [wellness] Классно. | quote: Классно.
key events: 1
- #9 CALL_ENDED 2026-09-14 00:03:34.016010+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fc3909d6 — 2026-09-14 00:05:23.595851+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "negative", "sleep": "Спал.", "wellness": "Ужасно."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ужасно.
- Vera: Скажите, а лекарства вы каждый день принимаете?
- User[u-2]: Нет.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-3]: Не удалось.
- Vera: А спалось сегодня нормально?
- User[u-4]: Спал.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-5]: Сердце умирало.
- Vera: Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.
observations: 9
- t3 [wellness] Ужасно. | quote: Ужасно.
- t3 [mood] negative | quote: negative
- t4 [wellness] Ужасно. | quote: Ужасно.
- t4 [mood] negative | quote: negative
- t5 [wellness] Ужасно. | quote: Ужасно.
- t5 [mood] negative | quote: negative
- t6 [wellness] Ужасно. | quote: Ужасно.
- t6 [mood] negative | quote: negative
- t6 [sleep] Спал. | quote: Спал.
key events: 1
- #9 CALL_ENDED 2026-09-14 00:05:23.597841+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d99db688 — 2026-09-14 00:22:58.874826+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Непонятно."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Непонятно.
- Vera: А таблетки вам каждый день назначены?
- User[u-2]: Это не назначено.
- Vera: А покушать сегодня уже успели?
- User[u-3]: Успели.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-4]: Голова кружится.
- Vera: Поняла вас. Голова кружится — зафиксировала. Когда кружится голова, вы можете уверенно стоять и ходить?
- User[u-5]: Ого.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили головная боль. На сегодня всё. Берегите себя. До свидания.
observations: 4
- t3 [wellness] Непонятно. | quote: Непонятно.
- t4 [wellness] Непонятно. | quote: Непонятно.
- t5 [wellness] Непонятно. | quote: Непонятно.
- t6 [wellness] Непонятно. | quote: Непонятно.
key events: 1
- #9 CALL_ENDED 2026-09-14 00:22:58.876997+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-b661257d — 2026-09-14 00:29:55.524688+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: Скажите, а лекарства вы каждый день принимаете?
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #4 WAIT_EXPIRED 2026-09-14 00:29:51.163464+00:00 {"turn_id": 3, "wait_id": "wait-background_medication", "pending_slot": "background_medication"}
- #6 CALL_ENDED 2026-09-14 00:29:55.527473+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-b7b2ba14 — 2026-09-14 00:30:30.126052+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-14 00:30:30.128590+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-9a2396b3 — 2026-09-14 00:32:43.566287+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо.
- Vera: А таблетки вам каждый день назначены?
- User[u-2]: Назначены.
- Vera: А таблетки вам каждый день назначены?
- User[u-3]: Не начено.
- Vera: А покушать сегодня уже успели?
- User[u-4]: Угу.
- User[u-5]: Успели.
- Vera: А покушать сегодня уже успели?
- User[u-6]: Угу.
observations: 5
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
- t7 [wellness] Хорошо. | quote: Хорошо.
key events: 1
- #10 CALL_ENDED 2026-09-14 00:32:43.568534+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-fe57cba6 — 2026-09-14 00:55:47.905264+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Ничего не тревожит.", "sleep": "Да, нормально спал.", "wellness": "Хорошо чувствую себя."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Хорошо чувствую себя.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-2]: Кушал.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-3]: Покушал и попил.
- Vera: Есть ли у вас лекарства, которые вы обычно принимаете?
- User[u-4]: Ну, кое-что есть. Сегодня весь день закрутился и вообще не помню, что там было утром.
- Vera: А настроение сегодня как — ничего не тревожит?
- User[u-5]: Ничего не тревожит.
- Vera: А спалось сегодня нормально?
- User[u-6]: Да, нормально спал.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-7]: Очи болит.
- Vera: Поняла вас. Болит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-8]: Ну вот я проснулся где-то в 6:00 утра, потому что мне нужно было выпить чай крепкий. А и потом вот после этого чё-то голова заболела.
- Vera: Хорошо. А сейчас голова ещё болит или уже почти прошла?
- User[u-9]: Почти прошла.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили болит и головная боль. На сегодня всё. Берегите себя. До свидания.
observations: 15
- t3 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t4 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t5 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t6 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t7 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t7 [mood] Ничего не тревожит. | quote: Ничего не тревожит.
- t8 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t8 [mood] Ничего не тревожит. | quote: Ничего не тревожит.
- t8 [sleep] Да, нормально спал. | quote: Да, нормально спал.
- t9 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t9 [mood] Ничего не тревожит. | quote: Ничего не тревожит.
- t9 [sleep] Да, нормально спал. | quote: Да, нормально спал.
- t10 [wellness] Хорошо чувствую себя. | quote: Хорошо чувствую себя.
- t10 [mood] Ничего не тревожит. | quote: Ничего не тревожит.
- t10 [sleep] Да, нормально спал. | quote: Да, нормально спал.
key events: 1
- #13 CALL_ENDED 2026-09-14 00:55:47.907673+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e2c73edf — 2026-09-14 00:57:07.801845+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"plans": "Дома что-то холодно, поэтому как будто чуть сонливость у меня небольшая. А так, в принципе, себя хорошо чувствую. Но ногу вот сегодня подвернуло, пот...
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Чувствую себя хорошо.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-2]: Покушал, но попить ещё не успел.
- Vera: Есть ли у вас лекарства, которые вы обычно принимаете?
- User[u-3]: Эту
- Vera: Есть ли у вас лекарства, которые вы обычно принимаете?
- User[u-4]: Это
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-5]: Дома что-то холодно, поэтому как будто чуть сонливость у меня небольшая. А так, в принципе, себя хорошо чувствую. Но ногу вот сегодня подвернуло, потому что на улице скользко, чуть нога бол
- Vera: Поняла вас. Нога болит — зафиксировала. Сейчас боль сильнее или уже становится легче?
- User[u-6]: Но ведь легче, лёд приложил и кремушком намазал. Вот лежу, отдыхаю с внуком пирожки кушаю.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили нога болит. На сегодня всё. Берегите себя. До свидания.
observations: 6
- t3 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t4 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t5 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t6 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t7 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t7 [plans] Дома что-то холодно, поэтому как будто чуть сонливость у меня небольшая. А так, в принципе, себя хорошо чувствую. Но ног | quote: Дома что-то холодно, поэтому как будто чуть сонливость у меня небольшая. А так, в принципе, себя хорошо чувствую. Но ног
key events: 1
- #10 CALL_ENDED 2026-09-14 00:57:07.803813+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-780904ae — 2026-09-14 00:58:05.867419+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "negative", "sleep": "Не выспался.", "wellness": "Ужасно."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ужасно.
- Vera: А покушать сегодня уже успели?
- User[u-2]: Успел.
- Vera: А покушать сегодня уже успели?
- User[u-3]: Не успел.
- Vera: Скажите, а у вас есть лекарства, которые вы принимаете обычно?
- User[u-4]: Есть, но не выпил. Не хочу пить таблетки.
- Vera: А ночью как спали — выспались?
- User[u-5]: Не выспался.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-6]: У меня болит сердце, я сейчас умру.
- Vera: Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.
observations: 11
- t3 [wellness] Ужасно. | quote: Ужасно.
- t3 [mood] negative | quote: negative
- t4 [wellness] Ужасно. | quote: Ужасно.
- t4 [mood] negative | quote: negative
- t5 [wellness] Ужасно. | quote: Ужасно.
- t5 [mood] negative | quote: negative
- t6 [wellness] Ужасно. | quote: Ужасно.
- t6 [mood] negative | quote: negative
- t7 [wellness] Ужасно. | quote: Ужасно.
- t7 [mood] negative | quote: negative
- t7 [sleep] Не выспался. | quote: Не выспался.
key events: 1
- #10 CALL_ENDED 2026-09-14 00:58:05.870070+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-6298a1a3 — 2026-09-14 01:00:49.233888+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"plans": "Живот немного побаливал после еды, но сейчас нормально. Ел сегодня мало, аппетита особого не было. Водик пил вроде нормально, слабость небольшая есть...
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас уже вроде прошла.
- Vera: Сегодня удалось хоть немного поесть и попить?
- User[u-2]: Есть удалось? Попить нет, хотя утром вроде бы пил.
- Vera: Есть ли у вас лекарства, которые вы обычно принимаете?
- User[u-3]: Таблетки у меня какие-то есть, но я не помню, пил сегодня или нет. Хотя может и пил утром, не уверен.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-4]: Живот немного побаливал после еды, но сейчас нормально. Ел сегодня мало, аппетита особого не было. Водик пил вроде нормально, слабость небольшая есть, но я сегодня выходил в магазин и ходит
- Vera: Поняла вас. Живот побаливал — зафиксировала. А живот сейчас ещё беспокоит или уже стало лучше?
- User[u-5]: Ну, стало лучше, но настроение у меня какое-то обычное, обычное, хотя одному дома скучновато. А что вы спрашивали про лекарства?
- Vera: Когда появилась эта слабость — сегодня или раньше?
- User[u-6]: Раньше, а что ты спрашивал меня про лекарства?
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили головная боль, плохой сон, боль в животе и слабость. На сегодня всё. Берегите себя. До свидания.
observations: 12
- t3 [wellness] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t3 [sleep] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t4 [wellness] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t4 [sleep] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t5 [wellness] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t5 [sleep] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t6 [wellness] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t6 [sleep] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t6 [plans] Живот немного побаливал после еды, но сейчас нормально. Ел сегодня мало, аппетита особого не было. Водик пил вроде норма | quote: Живот немного побаливал после еды, но сейчас нормально. Ел сегодня мало, аппетита особого не было. Водик пил вроде норма
- t7 [wellness] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t7 [sleep] Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у | quote: Вроде нормально себя чувствую, хотя ночью почти не спал, просыпался несколько раз. Утром голова немного болела, сейчас у
- t7 [plans] Живот немного побаливал после еды, но сейчас нормально. Ел сегодня мало, аппетита особого не было. Водик пил вроде норма | quote: Живот немного побаливал после еды, но сейчас нормально. Ел сегодня мало, аппетита особого не было. Водик пил вроде норма
key events: 1
- #10 CALL_ENDED 2026-09-14 01:00:49.236765+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0ed5232c — 2026-09-14 01:02:48.355041+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"sleep": "В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.", "wellness": "В целом нормально. Хотя, если честно, ночью спал бе...
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- Vera: А покушать сегодня уже успели?
- User[u-2]: А, вроде что-то перекусил, но без особого аппетита. Честно, просто не хотелось особо есть.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-3]: Наверное, да. Ещё есть такая вещь: голова немного побаливала с утра, но сейчас уже почти прошло, вроде терпимо.
- Vera: Поняла вас. Голова побаливала — зафиксировала. Боль сильная или терпимая?
- User[u-4]: Вот.
- Vera: Я вас слушаю. Боль сильная или терпимая?
- User[u-6]: Терпимая, не сильная, скорее фоновая, и она уже почти прошла. Сейчас больше просто усталость.
- Vera: Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.
observations: 8
- t3 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t3 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t4 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t4 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t5 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t5 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t6 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t6 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
key events: 1
- #9 CALL_ENDED 2026-09-14 01:02:48.356715+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-35e0a389 — 2026-09-14 09:56:05.382160+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-14 09:56:05.383931+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-10ca89ef — 2026-09-14 21:24:09.390130+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Ой, привет. Чувствую себя очень плохо. У меня голова болит и тошнотное состояние. Умираю, короче."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ой, привет. Чувствую себя очень плохо. У меня голова болит и тошнотное состояние. Умираю, короче.
- Vera: Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-14 21:24:09.392393+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0828912d — 2026-09-14 21:24:34.316514+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет, я умираю."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет, я умираю.
- Vera: Что именно беспокоит?
- User[u-2]: Что ещё раз?
- Vera: Да, слышу. Что именно беспокоит?
observations: 1
- t3 [wellness] Привет, я умираю. | quote: Привет, я умираю.
key events: 1
- #6 CALL_ENDED 2026-09-14 21:24:34.319113+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-92b2dd5a — 2026-09-14 23:14:45.895744+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:14:30.514936+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:14:45.898030+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d2e22096 — 2026-09-14 23:19:12.198606+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:18:56.803738+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:19:12.201100+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f72ec306 — 2026-09-14 23:20:59.325236+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:20:43.920723+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:20:59.327291+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-2f3363da — 2026-09-14 23:23:12.924211+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:22:57.535581+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:23:12.926831+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-1b3b90bd — 2026-09-14 23:33:47.203344+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:33:31.773649+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:33:47.204876+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-57aa6f3d — 2026-09-14 23:38:20.698845+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:38:05.305437+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:38:20.702106+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f8ee43b1 — 2026-09-14 23:47:12.234052+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:46:56.816026+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:47:12.236590+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f8fab6dc — 2026-09-14 23:47:30.509491+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:47:15.069366+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:47:30.511302+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-44fd798f — 2026-09-14 23:50:19.788908+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:50:04.427633+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:50:19.791841+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-2311dd4a — 2026-09-14 23:55:14.297687+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Чувствую себя великолепно."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Чувствую себя великолепно.
- Vera: Хорошо. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-2]: Не знаю.
- Vera: Спасибо, Даниил. На сегодня всё. Берегите себя. До свидания.
observations: 1
- t3 [wellness] Чувствую себя великолепно. | quote: Чувствую себя великолепно.
key events: 1
- #6 CALL_ENDED 2026-09-14 23:55:14.299507+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ddae11a2 — 2026-09-14 23:57:26.126721+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:57:10.755328+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:57:26.129433+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-e8e2400a — 2026-09-14 23:58:54.362693+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-14 23:58:38.992299+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-14 23:58:54.365617+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-4f2694c3 — 2026-09-15 00:01:10.408959+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-15 00:00:54.889705+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #6 CALL_ENDED 2026-09-15 00:01:10.411415+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ff2f66d2 — 2026-09-15 00:05:08.009581+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-15 00:05:08.011256+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a1dca80c — 2026-09-15 01:46:25.718972+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Я же говорю, чё-то и хорошо, и плохо мне.", "plans": "Пойдёт.", "sleep": "Пойдёт.", "wellness": "Да вроде бы и нормально чувствую, и в то же время пло...
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние.
- Vera: А покушать сегодня уже успели?
- User[u-3]: Да вроде бы поел.
- Vera: Скажите, а у вас есть лекарства, которые вы принимаете обычно?
- User[u-4]: Нет, лекарств никаких не надо принимать мне.
- Vera: Как настроение? Ничего не беспокоит?
- User[u-5]: Я же говорю, чё-то и хорошо, и плохо мне.
- Vera: А ночью как спали — выспались?
- User[u-6]: Пойдёт.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-7]: Наверное.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-8]: Нет, наверное, говорю.
- Vera: Сейчас не получилось узнать, как у вас дела. До свидания.
observations: 13
- t3 [wellness] Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние. | quote: Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние.
- t4 [wellness] Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние. | quote: Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние.
- t5 [wellness] Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние. | quote: Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние.
- t6 [wellness] Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние. | quote: Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние.
- t6 [mood] Я же говорю, чё-то и хорошо, и плохо мне. | quote: Я же говорю, чё-то и хорошо, и плохо мне.
- t7 [wellness] Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние. | quote: Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние.
- t7 [mood] Я же говорю, чё-то и хорошо, и плохо мне. | quote: Я же говорю, чё-то и хорошо, и плохо мне.
- t7 [sleep] Пойдёт. | quote: Пойдёт.
- t7 [plans] Пойдёт. | quote: Пойдёт.
- t8 [wellness] Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние. | quote: Да вроде бы и нормально чувствую, и в то же время плохо себя чувствую, что тут непонятное какое-то состояние.
- t8 [mood] Я же говорю, чё-то и хорошо, и плохо мне. | quote: Я же говорю, чё-то и хорошо, и плохо мне.
- t8 [sleep] Пойдёт. | quote: Пойдёт.
- t8 [plans] Пойдёт. | quote: Пойдёт.
key events: 1
- #11 CALL_ENDED 2026-09-15 01:46:25.721807+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-abffeb17 — 2026-09-15 01:58:00.186250+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Всё отвратительно, Вера."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Всё отвратительно, Вера.
- Vera: А покушать сегодня уже успели?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-15 01:58:00.189033+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e8164316 — 2026-09-15 02:05:43.037524+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя паршиво, плохо, отвратительно, дерьмово. Даже не передать словами."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет. Чувствую себя паршиво, плохо, отвратительно, дерьмово. Даже не передать словами.
- Vera: Сегодня удалось хоть немного поесть и попить?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-15 02:05:43.040523+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-d6e4dccb — 2026-09-15 02:18:51.877561+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Чувствуй себя плохо, отвратительно, вообще плохо ощущай себя."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Чувствуй себя плохо, отвратительно, вообще плохо ощущай себя.
- Vera: Как сегодня с едой — нормально поели?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-15 02:18:51.879821+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-70509d29 — 2026-09-15 13:07:25.655176+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Ой, чувствую себя очень плохо. Умираю. Такое состояние плохое у меня прям."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ой, чувствую себя очень плохо. Умираю. Такое состояние плохое у меня прям.
- Vera: Что именно беспокоит?
- User[u-2]: Ой, не могу даже сказать, что меня беспокоит. Но вот сердце покалывает, головная боль очень сильная, как будто вот, ну вот все кости ломит.
- Vera: Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.
observations: 1
- t3 [wellness] Ой, чувствую себя очень плохо. Умираю. Такое состояние плохое у меня прям. | quote: Ой, чувствую себя очень плохо. Умираю. Такое состояние плохое у меня прям.
key events: 1
- #6 CALL_ENDED 2026-09-15 13:07:25.656905+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-39cb7575 — 2026-09-15 13:08:01.084770+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Ну, более-менее, так, нормально."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ну, более-менее, так, нормально.
- Vera: Поняла вас. Более-менее — зафиксировала. Когда это началось — сегодня или раньше?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-15 13:08:01.087336+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-4bb9ac4c — 2026-09-15 22:27:07.754180+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-15 22:27:07.758631+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f184b782 — 2026-09-15 22:27:13.152006+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-15 22:27:13.154845+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0035db6c — 2026-09-16 01:51:50.425141+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет. Чувствую себя, ну, я не знаю, как сказать.
- Vera: Простите, не расслышала. Как вы себя чувствуете — хорошо или не очень?
observations: 0
key events: 1
- #5 CALL_ENDED 2026-09-16 01:51:50.428389+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-7be7ccda — 2026-09-16 02:08:08.661281+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Не очень."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ой, привет. Не знаю. Самочувствие такое непонятное.
- Vera: Простите, не расслышала. Как вы себя чувствуете — хорошо или не очень?
- User[u-2]: Ну, наверное, не очень.
- User[u-3]: Не очень.
- Vera: Что именно беспокоит?
- User[u-4]: Ой, не знаю. Ну вот-вот просто плохо мне.
- Vera: Скажите, что болит — голова, сердце, живот? Или что случилось?
- User[u-5]: Не знаю, вот фильм посмотрел и сразу плохо стало мне.
- Vera: Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.
observations: 2
- t4 [wellness] Не очень. | quote: Не очень.
- t5 [wellness] Не очень. | quote: Не очень.
key events: 1
- #8 CALL_ENDED 2026-09-16 02:08:08.665074+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f702d83e — 2026-09-16 13:37:41.812392+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Йой-ой-ой. Чувствую себя отвратительно, прямо вообще не знаю даже, как описать.
- Vera: Что именно беспокоит?
- User[u-2]: Ну, не знаю, Вера. Знаешь, вот такое состояние непонятное, то ли хорошо, то ли плохо.
- Vera: Как давно это продолжается?
- User[u-3]: Продолжительное время уже продолжается такое, уже два дня, наверное.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-4]: Наверное, только это было.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-5]: Я говорю: «Нет, наверное». Больше, наверное, ничего. Только это было.
- Vera: Спасибо, Даниил. На сегодня всё. Берегите себя. До свидания.
observations: 4
- t3 [wellness] negative | quote: negative
- t4 [wellness] negative | quote: negative
- t5 [wellness] negative | quote: negative
- t6 [wellness] negative | quote: negative
key events: 1
- #9 CALL_ENDED 2026-09-16 13:37:41.815151+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a6628c67 — 2026-09-17 01:12:16.446942+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ой, привет. Не знаю, как я себя чувствую.
- Vera: Простите, не расслышала. Как вы себя чувствуете — хорошо или не очень?
- User[u-2]: Ну
- User[u-3]: Вэу.
- Vera: Скажите просто: хорошо, нормально или плохо?
observations: 0
key events: 1
- #6 CALL_ENDED 2026-09-17 01:12:16.461444+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-98a7de1b — 2026-09-17 01:20:35.092997+00:00 (fsm=FINAL_CLASSIFICATION, termination=COMPLETED)

family=fam-voice ended=True
facts={"plans": "Да, сижу дома, кушаю, вот, хорошо себя вроде чувствую, всё нормально."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет. Не знаю.
- Vera: Простите, не расслышала. Как вы себя чувствуете — хорошо или не очень?
- User[u-2]: Не знаю, не могу сказать.
- Vera: Скажите просто: хорошо, нормально или плохо?
- User[u-3]: Наверное, среднее что-то.
- Vera: Не получается разобрать, я это запишу. Продолжим?
- User[u-4]: Да.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-5]: Да, сижу дома, кушаю, вот, хорошо себя вроде чувствую, всё нормально.
- Vera: Хорошо, записала. Спасибо, Даниил. На сегодня всё. Берегите себя. До свидания.
- User[u-6]: Да.
- Vera: До свидания, Даниил. Всего вам хорошего.
observations: 1
- t7 [plans] Да, сижу дома, кушаю, вот, хорошо себя вроде чувствую, всё нормально. | quote: Да, сижу дома, кушаю, вот, хорошо себя вроде чувствую, всё нормально.
key events: 1
- #10 CALL_ENDED 2026-09-17 01:20:35.098010+00:00 {"partial": true, "termination_reason": "COMPLETED"}

## fs-2bd8bf64 — 2026-09-17 22:41:49.448697+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "как себя чувствуешь"}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Ой, не знаю, как себя чувствуешь. Вроде плохо, вроде бы и хорошо.
- Vera: Что именно беспокоит?
- User[u-2]: Ну не знаю, то ли голова болит, то ли живот.
- Vera: Поняла вас. Голова болит — зафиксировала. Когда начала болеть голова — сегодня или раньше?
- User[u-3]: Вчера. Сейчас не болит.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-4]: Животик.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-5]: Животик болит.
- Vera: Поняла вас. Живот болит — зафиксировала. Когда это началось — сегодня или раньше?
- User[u-6]: Ну, сейчас начал болеть.
- Vera: Поняла вас. Болеть — зафиксировала. А живот сейчас ещё беспокоит или уже стало лучше?
- User[u-7]: Вот сейчас болит.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили головная боль, боль в животе и болеть. На сегодня всё. Берегите себя. До свидания.
observations: 6
- t3 [wellness] negative | quote: negative
- t4 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t5 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t6 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t7 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t8 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
key events: 1
- #11 CALL_ENDED 2026-09-17 22:41:49.452630+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c3cb344d — 2026-09-18 15:54:24.486498+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
observations: 0
key events: 1
- #4 CALL_ENDED 2026-09-18 15:54:24.492402+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-23d28835 — 2026-09-20 01:20:49.617186+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-20 01:20:30.864088+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": null}
- #6 CALL_ENDED 2026-09-20 01:20:49.625412+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-cbcd1f18 — 2026-09-20 01:21:00.780245+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-20 01:20:41.169332+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": null}
- #6 CALL_ENDED 2026-09-20 01:21:00.782843+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-723f04e0 — 2026-09-20 01:26:47.665696+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
- Vera: Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.
observations: 0
key events: 2
- #3 WAIT_EXPIRED 2026-09-20 01:26:28.526045+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": null}
- #6 CALL_ENDED 2026-09-20 01:26:47.668691+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-338ee6ab — 2026-09-20 01:34:28.660818+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя плохо."}
dialogue:
- Vera: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?
- User[u-1]: Привет. Чувствую себя плохо.
- Vera: Что именно беспокоит?
- User[u-2]: Не знаю, честно, то ли голова болит, то ли живот болит. Вот не знаю. И то, и то как будто бы болит.
- Vera: Поняла вас. Головная боль и боль в животе — это неприятно, давайте уточним по порядку. Когда начала болеть голова — сегодня или раньше?
- User[u-3]: Ну, не помню, во сколько начала болеть.
- Vera: Поняла вас. Болеть — зафиксировала. Когда начала болеть голова — сегодня или раньше?
- User[u-4]: Не знаю, когда болеть начало.
- Vera: Поняла вас. Болеть — зафиксировала. Боль сильная или терпимая?
- User[u-5]: Сильно.
- Vera: Хорошо. Когда это началось — сегодня или раньше?
- User[u-6]: Тоже не могу сказать, когда началось.
- Vera: Я вас слушаю. Когда это началось — сегодня или раньше?
- User[u-7]: Наверное, раннее.
- Vera: А живот сейчас ещё беспокоит или уже стало лучше?
- User[u-8]: Стало лучше.
- Vera: Когда это началось — сегодня или раньше?
- User[u-9]: Началось это ранее.
- Vera: Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии или дома, на что мне стоит обратить внимание?
- User[u-10]: Нет, нет, нет, нет, нет.
- Vera: Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно.
- User[u-11]: Ничего неважно. Всё, давай пока.
- Vera: Спасибо, Даниил. Я записала: сегодня беспокоили головная боль и боль в животе. На сегодня всё. Берегите себя. До свидания.
observations: 11
- t2 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t3 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t4 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t5 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t6 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t7 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t8 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t9 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t10 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t11 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
- t12 [wellness] Привет. Чувствую себя плохо. | quote: Привет. Чувствую себя плохо.
key events: 1
- #15 CALL_ENDED 2026-09-20 01:34:28.665852+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

calls with trace transcript: 214