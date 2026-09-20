# Live call log (lab, auto-exported from Postgres)

Exported: 2026-09-20T01:37:24.500506+00:00
Total calls: 263

## pg-8941eff458bd — 2026-09-06 13:44:36.926561+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-test ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:36.912427+00:00 {"family_id": "fam-pg-test"}
- #CALL_ENDED 2 2026-09-06 13:44:36.928085+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## pg-idem-0bc815f357e0 — 2026-09-06 13:44:36.970303+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-idem ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:36.957584+00:00 {"family_id": "fam-pg-idem"}
- #CALL_ENDED 2 2026-09-06 13:44:36.971966+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## say — 2026-09-06 13:44:40.323020+00:00 (fsm=CALL_START, termination=None)

family=fam-test ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 13:44:40.326161+00:00 {"family_id": "fam-test"}

## defer — 2026-09-06 13:44:40.482552+00:00 (fsm=FINAL_CLASSIFICATION, termination=DEFERRED)

family=fam-test ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:40.470043+00:00 {"family_id": "fam-test"}
- #CALL_ENDED 2 2026-09-06 13:44:40.483780+00:00 {"partial": true, "termination_reason": "DEFERRED"}

## wrong — 2026-09-06 13:44:40.507490+00:00 (fsm=FINAL_CLASSIFICATION, termination=WRONG_PERSON)

family=fam-test ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:40.495417+00:00 {"family_id": "fam-test"}
- #CALL_ENDED 2 2026-09-06 13:44:40.508710+00:00 {"partial": true, "termination_reason": "WRONG_PERSON"}

## consent — 2026-09-06 13:44:40.518386+00:00 (fsm=CALL_START, termination=None)

family=fam-test ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 13:44:40.520514+00:00 {"family_id": "fam-test"}

## pg-527462ecc106 — 2026-09-06 13:44:40.587692+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-test ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:40.577221+00:00 {"family_id": "fam-pg-test"}
- #CALL_ENDED 2 2026-09-06 13:44:40.589523+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## pg-idem-00ede56e0bb5 — 2026-09-06 13:44:40.626780+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-idem ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:40.616025+00:00 {"family_id": "fam-pg-idem"}
- #CALL_ENDED 2 2026-09-06 13:44:40.628020+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## audit — 2026-09-06 13:44:40.755677+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_REVOKED)

family=fam-test ended=True
facts={"plans": "весь день буду дома", "sleep": "плохо спала"}
observations: 4
- t2 [wellness] Пока всё хорошо | quote: Пока всё хорошо
- t2 [sleep] плохо спала | quote: плохо спала
- t2 [plans] весь день буду дома | quote: весь день буду дома
- t2 [None] я упала и не могу встать | quote: я упала и не могу встать
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:40.340012+00:00 {"family_id": "fam-test"}
- #CALL_ENDED 2 2026-09-06 13:44:40.458131+00:00 {"partial": true, "termination_reason": "CONSENT_REVOKED"}

## term — 2026-09-06 13:44:40.794207+00:00 (fsm=FINAL_CLASSIFICATION, termination=None)

family=fam-test ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 13:44:40.533194+00:00 {"family_id": "fam-test"}
- #CALL_ENDED 2 2026-09-06 13:44:40.795415+00:00 {"partial": true, "termination_reason": null}

## sip-421fbc79df — 2026-09-06 15:12:30.686249+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:09:39.802026+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:12:30.693672+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-f137ff41b9 — 2026-09-06 15:12:54.895514+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:12:38.858392+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:12:54.901070+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-3985072e1d — 2026-09-06 15:14:31.836053+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:13:27.780463+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:14:31.839922+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## media-48defbc1 — 2026-09-06 15:15:24.382730+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:15:10.905579+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:15:24.387179+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## media-ac14d2b2 — 2026-09-06 15:16:04.668050+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:15:39.548355+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:16:04.672949+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-7804ea125c — 2026-09-06 15:16:37.144267+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 15:16:37.151204+00:00 {"family_id": "fam-voice"}

## sip-0800c3410d — 2026-09-06 15:18:24.699496+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 15:18:24.706283+00:00 {"family_id": "fam-voice"}

## sip-51953e0761 — 2026-09-06 15:23:37.980431+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:22:39.199994+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:23:37.983886+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-926cfc81ba — 2026-09-06 15:24:44.242814+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:23:48.709437+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:24:44.246865+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b115e2258d — 2026-09-06 15:25:51.671442+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:24:55.239624+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:25:51.674662+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b7a50e9cb9 — 2026-09-06 15:27:57.462223+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:27:00.310022+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:27:57.465614+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9c972fcdb9 — 2026-09-06 15:43:54.006833+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 15:43:54.016440+00:00 {"family_id": "fam-voice"}

## sip-0a94a47d05 — 2026-09-06 15:48:41.534970+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 15:42:52.451605+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 15:48:41.543828+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-67e737febb — 2026-09-06 17:12:07.870551+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 17:11:35.908704+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 17:12:07.878108+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ecc9455ec2 — 2026-09-06 17:13:14.413604+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 17:13:14.421159+00:00 {"family_id": "fam-voice"}

## sip-5085974b40 — 2026-09-06 17:14:01.841362+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 17:14:01.848474+00:00 {"family_id": "fam-voice"}

## sip-fb37304784 — 2026-09-06 17:17:49.525192+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 17:12:42.382881+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 17:17:49.528445+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-f1d913bcd9 — 2026-09-06 20:06:08.512092+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 20:05:57.189651+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 20:06:08.519678+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-d98b9bd3a6 — 2026-09-06 20:20:52.677313+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 20:20:47.409452+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 20:20:52.683717+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9c081a1acf — 2026-09-06 20:51:49.900642+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 20:50:50.861093+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 20:51:49.906875+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-3a46ad0ec9 — 2026-09-06 20:53:15.151056+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 20:52:11.179989+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 20:53:15.155445+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-cf08b1d6fe — 2026-09-06 20:53:50.816821+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 20:53:45.211868+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 20:53:50.819461+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-08254739f0 — 2026-09-06 20:55:30.052728+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 20:54:57.993910+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 20:55:30.057630+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-03a8e26a72 — 2026-09-06 21:08:37.015720+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:08:30.912622+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:08:37.019820+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-a66024f7fa — 2026-09-06 21:09:58.980553+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:08:54.910237+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:09:58.983726+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-4fb275716a — 2026-09-06 21:13:39.487942+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:13:31.304856+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:13:39.491132+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-5e71376cd1 — 2026-09-06 21:18:38.906416+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:17:34.770299+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:18:38.912249+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-42c829d3a9 — 2026-09-06 21:19:07.297996+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:18:51.633437+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:19:07.305058+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-6db41a1f74 — 2026-09-06 21:19:19.026849+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:19:07.332307+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:19:19.031913+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-2e5bc8aec8 — 2026-09-06 21:20:23.115847+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:19:19.050905+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:20:23.120174+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-24704f379e — 2026-09-06 21:33:42.228274+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:33:38.723029+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:33:42.372356+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-99de797ab5 — 2026-09-06 21:34:41.363441+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:34:32.686860+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:34:41.365704+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b2e42437e4 — 2026-09-06 21:38:59.236872+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:37:55.182704+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:38:59.239645+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-8e313ca55f — 2026-09-06 21:43:33.125197+00:00 (fsm=CALL_START, termination=None)

family=fam-voice ended=False
facts={}
observations: 0
key events: 1
- #CALL_STARTED 1 2026-09-06 21:43:33.142210+00:00 {"family_id": "fam-voice"}

## sip-3fa2420f27 — 2026-09-06 21:59:08.750333+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 21:58:58.886278+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 21:59:08.755887+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-956145c520 — 2026-09-06 22:21:46.196287+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:21:14.169171+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:21:46.200842+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-906515a8e9 — 2026-09-06 22:23:18.032860+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:22:52.214481+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:23:18.037003+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9606317380 — 2026-09-06 22:23:51.086976+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:23:41.495527+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:23:51.091729+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-74b2db1134 — 2026-09-06 22:24:39.173185+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:24:30.999239+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:24:39.176451+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-e8ba5b2594 — 2026-09-06 22:31:17.071089+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:30:13.015867+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:31:17.074107+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ee14384e11 — 2026-09-06 22:32:32.911886+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:32:22.013362+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:32:32.914118+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-16a64c0b56 — 2026-09-06 22:34:54.125131+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:34:45.729917+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:34:54.129426+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-1aa441cc86 — 2026-09-06 22:44:28.298204+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:43:56.228934+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:44:28.301180+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-2a044fd4e2 — 2026-09-06 22:52:48.298968+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 22:52:16.240821+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 22:52:48.302079+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-0016cdc5bd — 2026-09-06 23:17:34.288405+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-06 23:17:24.644561+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-06 23:17:34.291718+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b5dbbb12df — 2026-09-07 00:03:05.137094+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:02:01.102076+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:03:05.141372+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-bf416eca2a — 2026-09-07 00:22:20.407872+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:22:10.018273+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:22:20.414222+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-271cbbb67f — 2026-09-07 00:37:35.298848+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:36:31.245287+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:37:35.301969+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-45b72499c6 — 2026-09-07 00:39:30.117533+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:38:26.124839+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:39:30.129307+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-d03cd54d75 — 2026-09-07 00:39:58.103936+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:39:47.966819+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:39:58.108223+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-a3d6d9e32f — 2026-09-07 00:43:48.008331+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:42:43.950909+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:43:48.014626+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-c570309cb5 — 2026-09-07 00:45:31.378986+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:45:21.891101+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:45:31.389970+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## e2e-34c91eeb — 2026-09-07 00:46:34.996777+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:46:34.489594+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:46:35.001061+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-39222a6a84 — 2026-09-07 00:50:18.296607+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:49:14.300129+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:50:18.301528+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-340ea83659 — 2026-09-07 00:51:01.360623+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:50:41.975535+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:51:01.364115+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-fe2577c23f — 2026-09-07 00:53:02.956875+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 9
- #CALL_STARTED 1 2026-09-07 00:51:58.955384+00:00 {"family_id": "fam-voice"}
- #PLANNER_DECISION 2 2026-09-07 00:52:13.181573+00:00 {"intent": "confirm_identity", "turn_id": 2, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-1", "state_version...
- #PLANNER_DECISION 3 2026-09-07 00:52:22.849898+00:00 {"intent": "confirm_identity", "turn_id": 3, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-2", "state_version...
- #PLANNER_DECISION 4 2026-09-07 00:52:29.563154+00:00 {"intent": "confirm_identity", "turn_id": 4, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-3", "state_version...
- #PLANNER_DECISION 5 2026-09-07 00:52:35.346639+00:00 {"intent": "confirm_identity", "turn_id": 5, "user_act": "backchannel", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-4", "state_vers...
- #PLANNER_DECISION 6 2026-09-07 00:52:43.570990+00:00 {"intent": "confirm_identity", "turn_id": 6, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-5", "state_version...
- #PLANNER_DECISION 7 2026-09-07 00:52:51.430249+00:00 {"intent": "confirm_identity", "turn_id": 7, "user_act": "backchannel", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-6", "state_vers...
- #PLANNER_DECISION 8 2026-09-07 00:52:59.132218+00:00 {"intent": "confirm_identity", "turn_id": 8, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-7", "state_version...
- #CALL_ENDED 9 2026-09-07 00:53:02.961566+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-4db99c2384 — 2026-09-07 00:57:09.000747+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:56:05.012869+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 00:57:09.005897+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b7257cbdf5 — 2026-09-07 01:00:33.826471+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 00:59:29.845059+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 01:00:33.833765+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ec7c5f261a — 2026-09-07 01:11:21.694304+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 01:10:17.696861+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 01:11:21.698421+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-fbd5f14cf6 — 2026-09-07 01:13:35.192585+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 01:12:31.212685+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 01:13:35.196683+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-2af6c5d27d — 2026-09-07 01:28:37.736875+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 01:17:49.868338+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 01:28:37.740835+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ae8a649497 — 2026-09-07 02:18:42.935636+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 02:00:38.697400+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 02:18:42.939066+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-45eca01885 — 2026-09-07 13:50:25.994813+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 13:50:14.984346+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 13:50:25.998319+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-e35132246e — 2026-09-07 13:51:16.326227+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 13:50:26.012846+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 13:51:16.330132+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-3f95641c5b — 2026-09-07 13:52:46.645501+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 13:51:42.677715+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 13:52:46.650535+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-cdeeb202ed — 2026-09-07 13:54:29.729238+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 13:53:43.633982+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 13:54:29.732372+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-e912f033be — 2026-09-07 13:56:42.817354+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 13:56:33.568015+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 13:56:42.819939+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-408e3037fa — 2026-09-07 14:01:08.262684+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:00:04.208617+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:01:08.266637+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-be05fb81e2 — 2026-09-07 14:02:57.929204+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:01:53.862718+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:02:57.933595+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-1b01fd590a — 2026-09-07 14:03:47.582720+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:03:42.712223+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:03:47.588455+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-deac07be2a — 2026-09-07 14:05:30.178107+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:04:26.110973+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:05:30.180779+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-c5dbd3f4de — 2026-09-07 14:07:51.740113+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-07 14:06:47.704786+00:00 {"family_id": "fam-voice"}
- #PLANNER_DECISION 2 2026-09-07 14:07:03.871756+00:00 {"intent": "confirm_identity", "turn_id": 2, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-1", "state_version...
- #PLANNER_DECISION 3 2026-09-07 14:07:11.760664+00:00 {"intent": "confirm_identity", "turn_id": 3, "user_act": "question", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-2", "state_version...
- #PLANNER_DECISION 4 2026-09-07 14:07:17.574250+00:00 {"intent": "confirm_identity", "turn_id": 4, "user_act": "backchannel", "fsm_state": "IDENTIFY_PERSON", "pending_slot": null, "utterance_id": "u-3", "state_vers...
- #CALL_ENDED 5 2026-09-07 14:07:51.746403+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-9aac723ad4 — 2026-09-07 14:10:52.402466+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:09:48.416413+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:10:52.408516+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-22797b6f1e — 2026-09-07 14:12:18.161462+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:11:14.104232+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:12:18.165656+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ffbcac8dc2 — 2026-09-07 14:14:10.130310+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:13:06.082545+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:14:10.134167+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-04c5548d77 — 2026-09-07 14:16:06.822529+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 14:15:02.777817+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 14:16:06.826655+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b5d126a19c — 2026-09-07 17:11:50.076082+00:00 (fsm=IDENTIFY_PERSON, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 17:10:46.033833+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 17:11:50.082104+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-31365dee13 — 2026-09-07 21:08:24.081033+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-07 21:08:15.152835+00:00 {"family_id": "fam-voice"}
- #PLANNER_DECISION 2 2026-09-07 21:08:21.687899+00:00 {"intent": "partial_unresolved_close", "turn_id": 2, "user_act": "question", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "utterance_id": "u-1", "...
- #CALL_ENDED 3 2026-09-07 21:08:21.745068+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-4e3e327b7a — 2026-09-07 21:21:17.038206+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 21:20:12.982503+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 21:21:17.040618+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-97e9d693a5 — 2026-09-07 21:29:59.230432+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 21:28:55.200473+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 21:29:59.233280+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-b3212ad847 — 2026-09-07 21:31:54.120665+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 21:30:50.060087+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 21:31:54.125626+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-1b47b87d75 — 2026-09-07 21:51:07.111181+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 21:50:03.054513+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 21:51:07.115176+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-dad36ca2bf — 2026-09-07 21:52:49.732497+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 21:51:45.656269+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 21:52:49.740353+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-f0aec9372b — 2026-09-07 22:13:34.303233+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-07 22:13:07.045468+00:00 {"family_id": "fam-voice"}
- #WAIT_EXPIRED 2 2026-09-07 22:13:18.802692+00:00 {"turn_id": 2, "wait_id": "wait-66924cc97dfe", "pending_slot": "wellness"}
- #WAIT_EXPIRED 3 2026-09-07 22:13:28.616396+00:00 {"turn_id": 3, "wait_id": "wait-a7bbe2dd8861", "pending_slot": "wellness"}
- #CALL_ENDED 4 2026-09-07 22:13:28.656745+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-55bcd86150 — 2026-09-07 22:38:30.065151+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 22:38:21.767026+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 22:38:30.069822+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-442a841336 — 2026-09-07 22:38:57.320160+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-07 22:38:30.102701+00:00 {"family_id": "fam-voice"}
- #WAIT_EXPIRED 2 2026-09-07 22:38:41.728396+00:00 {"turn_id": 2, "wait_id": "wait-01628829d0ea", "pending_slot": "wellness"}
- #WAIT_EXPIRED 3 2026-09-07 22:38:51.702908+00:00 {"turn_id": 3, "wait_id": "wait-90f55718a3a5", "pending_slot": "wellness"}
- #CALL_ENDED 4 2026-09-07 22:38:51.768287+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-f21993a04f — 2026-09-07 22:45:25.936014+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-07 22:45:13.001209+00:00 {"family_id": "fam-voice"}
- #WAIT_EXPIRED 2 2026-09-07 22:45:24.535051+00:00 {"turn_id": 2, "wait_id": "wait-b900a59f72af", "pending_slot": "wellness"}
- #CALL_ENDED 3 2026-09-07 22:45:25.938602+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-023339de5e — 2026-09-07 23:14:40.946316+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-07 23:14:13.782958+00:00 {"family_id": "fam-voice"}
- #WAIT_EXPIRED 2 2026-09-07 23:14:25.220191+00:00 {"turn_id": 2, "wait_id": "wait-7e285a9a1743", "pending_slot": "wellness"}
- #WAIT_EXPIRED 3 2026-09-07 23:14:34.817976+00:00 {"turn_id": 3, "wait_id": "wait-26fc8af4d8cb", "pending_slot": "wellness"}
- #CALL_ENDED 4 2026-09-07 23:14:34.886063+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-d6a2e17c40 — 2026-09-07 23:17:00.511100+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Как вы себя чувствуете?"}
observations: 1
- t2 [wellness] Как вы себя чувствуете? | quote: Как вы себя чувствуете?
key events: 5
- #CALL_STARTED 1 2026-09-07 23:16:28.219326+00:00 {"family_id": "fam-voice"}
- #PLANNER_DECISION 2 2026-09-07 23:16:39.054701+00:00 {"intent": "check_mood", "turn_id": 2, "user_act": "answer", "fsm_state": "DAILY_CHECK", "pending_slot": "mood", "utterance_id": "u-1", "state_version": 4}
- #WAIT_EXPIRED 3 2026-09-07 23:16:48.348077+00:00 {"turn_id": 3, "wait_id": "wait-affb62f2d10e", "pending_slot": "mood"}
- #WAIT_EXPIRED 4 2026-09-07 23:16:57.858144+00:00 {"turn_id": 4, "wait_id": "wait-256f67048a6f", "pending_slot": "mood"}
- #CALL_ENDED 5 2026-09-07 23:16:57.932013+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## sip-93be0754bc — 2026-09-07 23:40:39.118787+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-07 23:40:11.469589+00:00 {"family_id": "fam-voice"}
- #WAIT_EXPIRED 2 2026-09-07 23:40:23.284542+00:00 {"turn_id": 2, "wait_id": "wait-075d6a4a7344", "pending_slot": "wellness"}
- #WAIT_EXPIRED 3 2026-09-07 23:40:33.093940+00:00 {"turn_id": 3, "wait_id": "wait-40e50e3c0f22", "pending_slot": "wellness"}
- #CALL_ENDED 4 2026-09-07 23:40:33.166315+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## gate-smoke — 2026-09-07 23:59:36.417740+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-07 20:29:13.665464+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-07 20:29:13.692806+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-44dc10cc5d — 2026-09-08 00:01:33.018277+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-08 00:01:00.965245+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-08 00:01:33.022125+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-4447e6c637 — 2026-09-08 00:03:40.707662+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-08 00:03:08.636965+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-08 00:03:40.711340+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-617ad9e4a0 — 2026-09-08 00:04:21.758892+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-08 00:03:49.717344+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-08 00:04:21.761930+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-62899e9c4e — 2026-09-08 00:05:46.105114+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-08 00:04:42.054016+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-08 00:05:46.107771+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-d23efc992a — 2026-09-08 00:52:58.869609+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-08 00:52:26.824266+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-08 00:52:58.872019+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## sip-ab5b721049 — 2026-09-08 01:06:22.640748+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 2
- #CALL_STARTED 1 2026-09-08 01:05:50.604951+00:00 {"family_id": "fam-voice"}
- #CALL_ENDED 2 2026-09-08 01:06:22.644218+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-df75c08d — 2026-09-08 12:38:27.514306+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 12:38:10.432754+00:00 {"family_id": "fam-voice"}
- #WAIT_EXPIRED 2 2026-09-08 12:38:18.070285+00:00 {"turn_id": 2, "wait_id": "wait-0b16253dc14c", "pending_slot": "wellness"}
- #WAIT_EXPIRED 3 2026-09-08 12:38:26.367413+00:00 {"turn_id": 3, "wait_id": "wait-d3116f041e18", "pending_slot": "wellness"}
- #CALL_ENDED 4 2026-09-08 12:38:26.431108+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-a1f760cf — 2026-09-08 12:52:45.015526+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 12:52:27.661136+00:00 {"family_id": "fam-voice"}
- #WAIT_EXPIRED 2 2026-09-08 12:52:35.289473+00:00 {"turn_id": 2, "wait_id": "wait-96e4046607f7", "pending_slot": "wellness"}
- #WAIT_EXPIRED 3 2026-09-08 12:52:43.772287+00:00 {"turn_id": 3, "wait_id": "wait-72d9c0a31028", "pending_slot": "wellness"}
- #CALL_ENDED 4 2026-09-08 12:52:43.841366+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f0daadb9 — 2026-09-08 13:00:59.133337+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо себя чувствую"}
observations: 2
- t2 [wellness] Чувствую себя хорошо | quote: Привет. Чувствую себя хорошо.
- t4 [wellness] Хорошо себя чувствую | quote: Хорошо себя чувствую.
key events: 5
- #CALL_STARTED 1 2026-09-08 13:00:21.294279+00:00 {"family_id": "fam-voice"}
- #PLANNER_DECISION 2 2026-09-08 13:00:38.285776+00:00 {"intent": "check_mood", "turn_id": 2, "user_act": "question", "fsm_state": "DAILY_CHECK", "pending_slot": "mood", "utterance_id": "u-1", "state_version": 4}
- #PLANNER_DECISION 3 2026-09-08 13:00:45.831305+00:00 {"intent": "check_mood", "turn_id": 3, "user_act": "question", "fsm_state": "DAILY_CHECK", "pending_slot": "mood", "utterance_id": "u-2", "state_version": 6}
- #PLANNER_DECISION 4 2026-09-08 13:00:57.877627+00:00 {"intent": "partial_unresolved_close", "turn_id": 4, "user_act": "answer", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "utterance_id": "u-3", "st...
- #CALL_ENDED 5 2026-09-08 13:00:57.960573+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-14c79443 — 2026-09-08 14:05:36.850174+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Хорошее настроение.", "plans": "А нас нету, в больницу пойду.", "sleep": "спал сегодня", "wellness": "хорошо"}
observations: 6
- t3 [wellness] хорошо | quote: хорошо
- t4 [wellness] хорошо | quote: хорошо
- t4 [mood] Хорошее настроение. | quote: Хорошее настроение.
- t5 [wellness] хорошо | quote: хорошо
- t5 [mood] Хорошее настроение. | quote: Хорошее настроение.
- t5 [sleep] спал сегодня | quote: спал сегодня
key events: 7
- #CALL_STARTED 1 2026-09-08 14:03:32.017139+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 14:03:32.043676+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 14:03:46.561485+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 14:03:53.121129+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-08 14:04:05.044172+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-08 14:04:18.021458+00:00 {"intent": "answer", "turn_id": 5, "revision": 10, "answer_slot": "plans", "skip_planner": true, "utterance_id": "u-4"}
- #CALL_ENDED 7 2026-09-08 14:05:36.852632+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e9717542 — 2026-09-08 15:09:06.314633+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое", "plans": "Никаких планов нет.", "sleep": "Плохо.", "wellness": "Тебе плохо."}
observations: 6
- t4 [wellness] Тебе плохо. | quote: Тебе плохо.
- t5 [wellness] Тебе плохо. | quote: Тебе плохо.
- t5 [mood] Плохое | quote: Плохое
- t6 [wellness] Тебе плохо. | quote: Тебе плохо.
- t6 [mood] Плохое | quote: Плохое
- t6 [sleep] Плохо. | quote: Плохо.
key events: 8
- #CALL_STARTED 1 2026-09-08 15:08:20.520799+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 15:08:20.560407+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 15:08:25.715389+00:00 {"intent": "backchannel", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 15:08:34.817142+00:00 {"intent": "answer", "turn_id": 3, "revision": 4, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-08 15:08:47.540844+00:00 {"intent": "answer", "turn_id": 4, "revision": 6, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-08 15:08:51.592618+00:00 {"intent": "answer", "turn_id": 5, "revision": 8, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-08 15:09:04.182014+00:00 {"intent": "answer", "turn_id": 6, "revision": 11, "answer_slot": "plans", "skip_planner": true, "utterance_id": "u-5"}
- #CALL_ENDED 8 2026-09-08 15:09:06.317456+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1be8664c — 2026-09-08 16:42:34.495249+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-08 16:42:20.151169+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 16:42:20.176258+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #CALL_ENDED 3 2026-09-08 16:42:34.501082+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1fbe9a6a — 2026-09-08 16:45:52.007757+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое.", "sleep": "Плохо.", "wellness": "Хорошо."}
observations: 3
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t4 [mood] Плохое. | quote: Плохое.
key events: 6
- #CALL_STARTED 1 2026-09-08 16:44:50.489253+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 16:44:50.511862+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 16:44:59.036169+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 4 2026-09-08 16:45:16.495624+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 5 2026-09-08 16:45:21.348020+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #CALL_ENDED 6 2026-09-08 16:45:52.011542+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-28767ff2 — 2026-09-08 18:28:51.249849+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 18:28:19.311930+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 18:28:19.341435+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 18:28:26.624628+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 18:28:51.252109+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ab822346 — 2026-09-08 18:28:58.343743+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 18:28:26.411052+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 18:28:26.441365+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 18:28:33.732609+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 18:28:58.346563+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-68d06379 — 2026-09-08 18:29:03.849401+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "плохо себя чувствуешь", "sleep": "Плохо.", "wellness": "Хорошо."}
observations: 4
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t5 [mood] плохо себя чувствуешь | quote: плохо себя чувствуешь
key events: 7
- #CALL_STARTED 1 2026-09-08 18:28:10.652929+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 18:28:10.683169+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 18:28:20.705632+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 18:28:31.272719+00:00 {"intent": "unclear", "turn_id": 3, "revision": 5, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-08 18:28:45.054073+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-08 18:28:50.369175+00:00 {"intent": "answer", "turn_id": 5, "revision": 9, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-4"}
- #CALL_ENDED 7 2026-09-08 18:29:03.851858+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-6c51dbdd — 2026-09-08 18:49:49.948199+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 18:49:18.041266+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 18:49:18.064611+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 18:49:25.375228+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 18:49:49.953903+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-5942df8c — 2026-09-08 18:49:57.139983+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 18:49:25.188716+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 18:49:25.214694+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 18:49:32.498469+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 18:49:57.143429+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-c663ec9b — 2026-09-08 20:40:45.314104+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:40:13.520584+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:40:13.579099+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:40:20.920459+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:40:45.321060+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-40b11c29 — 2026-09-08 20:45:43.447101+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:45:11.511929+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:45:11.535475+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:45:18.872857+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:45:43.453154+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-a7077bbc — 2026-09-08 20:50:08.376763+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:49:36.468130+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:49:36.495016+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:49:43.799942+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:50:08.381516+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d35beada — 2026-09-08 20:51:18.160625+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:50:46.191829+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:50:46.215157+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:50:53.515149+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:51:18.163589+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0336ed66 — 2026-09-08 20:53:08.497494+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:52:36.553958+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:52:36.579014+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:52:43.888172+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:53:08.502344+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-68dee177 — 2026-09-08 20:54:27.026444+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:53:55.049810+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:53:55.068023+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:54:02.370176+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:54:27.029918+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-c050c040 — 2026-09-08 20:57:22.123905+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:56:50.229089+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:56:50.250924+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:56:57.560206+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:57:22.126534+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-cf7610ae — 2026-09-08 20:59:25.764454+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:58:53.822816+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:58:53.847238+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:59:01.178798+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 20:59:25.768995+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0cc436e2 — 2026-09-08 21:00:08.164120+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 20:59:36.225928+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 20:59:36.251900+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 20:59:43.557343+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:00:08.167859+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f8fe6817 — 2026-09-08 21:00:58.697404+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:00:26.752746+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:00:26.778988+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:00:34.155607+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:00:58.700386+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fb8075a7 — 2026-09-08 21:01:37.504677+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:01:05.550783+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:01:05.576264+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:01:12.889352+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:01:37.508339+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0fbfe4b5 — 2026-09-08 21:02:51.331143+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:02:19.429493+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:02:19.451691+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:02:26.747567+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:02:51.334874+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f1173aac — 2026-09-08 21:04:59.384616+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:04:27.479503+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:04:27.504989+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:04:34.806657+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:04:59.388371+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-7b130bc8 — 2026-09-08 21:06:07.678893+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:05:35.725985+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:05:35.747060+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:05:43.049836+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:06:07.682930+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-b4a924d5 — 2026-09-08 21:07:16.975011+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:06:45.039175+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:06:45.065328+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:06:52.367038+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:07:16.977549+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-86fad0fa — 2026-09-08 21:08:53.136642+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:08:21.204779+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:08:21.245602+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:08:28.550066+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:08:53.143219+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-61e8f675 — 2026-09-08 21:10:10.775065+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:09:38.825989+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:09:38.856577+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:09:46.160059+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:10:10.777649+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-3adf104b — 2026-09-08 21:11:02.014744+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:10:30.086577+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:10:30.110864+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:10:37.413808+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:11:02.017034+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-124baeda — 2026-09-08 21:12:13.832170+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:11:41.867948+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:11:41.895010+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:11:49.182373+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:12:13.835110+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-2d125158 — 2026-09-08 21:13:14.884417+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:12:42.937122+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:12:42.962384+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:12:50.268836+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:13:14.888884+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-09ae279f — 2026-09-08 21:14:19.502465+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:13:47.605574+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:13:47.637509+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:13:54.929405+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:14:19.505560+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f3338b92 — 2026-09-08 21:15:09.410498+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:14:37.469161+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:14:37.496032+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:14:44.782200+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:15:09.413560+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-29b50e8a — 2026-09-08 21:24:18.500055+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое настроение. Говорю, самочувствие плохое.", "sleep": "Плохо.", "wellness": "Хорошо чувствую себя, но состояние не очень."}
observations: 3
- t3 [wellness] Хорошо чувствую себя, но состояние не очень. | quote: Хорошо чувствую себя, но состояние не очень.
- t4 [wellness] Хорошо чувствую себя, но состояние не очень. | quote: Хорошо чувствую себя, но состояние не очень.
- t4 [mood] Плохое настроение. Говорю, самочувствие плохое. | quote: Плохое настроение. Говорю, самочувствие плохое.
key events: 7
- #CALL_STARTED 1 2026-09-08 21:23:30.735043+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:23:30.765437+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 21:23:43.017155+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 21:23:51.716026+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-08 21:23:56.726283+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-3"}
- #WAIT_EXPIRED 6 2026-09-08 21:24:04.459760+00:00 {"turn_id": 5, "wait_id": "wait-plans", "pending_slot": "plans"}
- #CALL_ENDED 7 2026-09-08 21:24:18.503693+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-894c4326 — 2026-09-08 21:29:52.345452+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-08 21:29:05.287086+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:29:05.309502+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-08 21:29:12.943908+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-08 21:29:52.350609+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-69bd676a — 2026-09-08 21:42:26.276854+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое настроение, говорю.", "plans": "А сидеть дома, ничего не делать.", "sleep": "Плохо.", "wellness": "Я чувствую себя плохо."}
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
key events: 9
- #CALL_STARTED 1 2026-09-08 21:39:42.558368+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 21:39:42.583032+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 21:39:53.384839+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 21:40:16.483875+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-08 21:40:21.594425+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 6 2026-09-08 21:40:31.184654+00:00 {"intent": "answer", "turn_id": 5, "revision": 10, "answer_slot": "plans", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 7 2026-09-08 21:41:31.934128+00:00 {"intent": "unclear", "turn_id": 6, "revision": 11, "answer_slot": null, "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 8 2026-09-08 21:41:52.231861+00:00 {"intent": "answer", "turn_id": 7, "revision": 12, "answer_slot": null, "skip_planner": true, "utterance_id": "u-7"}
- #CALL_ENDED 9 2026-09-08 21:42:26.282218+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-8054b8c5 — 2026-09-08 22:08:02.399909+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Ну, из-за того, что голова болит, плохое настроение.", "plans": "Планов никаких нету.", "sleep": "Пойдёт, нормально.", "wellness": "Плохо."}
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
key events: 10
- #CALL_STARTED 1 2026-09-08 22:06:47.968376+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 22:06:47.993914+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 22:06:58.476042+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 22:07:07.096667+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "probe_concern", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-08 22:07:14.307113+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-08 22:07:24.163983+00:00 {"intent": "answer", "turn_id": 5, "revision": 9, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-08 22:07:30.336632+00:00 {"intent": "answer", "turn_id": 6, "revision": 11, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-08 22:07:38.949181+00:00 {"intent": "answer", "turn_id": 7, "revision": 14, "answer_slot": "plans", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-08 22:07:53.453380+00:00 {"intent": "answer", "turn_id": 8, "revision": 15, "answer_slot": null, "skip_planner": true, "utterance_id": "u-7"}
- #CALL_ENDED 10 2026-09-08 22:08:02.402736+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-3238b70a — 2026-09-08 22:31:26.809534+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Не очень, на самом деле, настроение у меня.", "plans": "Планов нету на сегодня.", "sleep": "Плохо спал. Ну так, хорошо. Спал хорошо.", "wellness": "Чу...
observations: 8
- t3 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t4 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t5 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t6 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t6 [mood] Не очень, на самом деле, настроение у меня. | quote: Не очень, на самом деле, настроение у меня.
- t7 [wellness] Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит. | quote: Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.
- t7 [mood] Не очень, на самом деле, настроение у меня. | quote: Не очень, на самом деле, настроение у меня.
- t7 [sleep] Плохо спал. Ну так, хорошо. Спал хорошо. | quote: Плохо спал. Ну так, хорошо. Спал хорошо.
key events: 9
- #CALL_STARTED 1 2026-09-08 22:30:04.974469+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 22:30:05.003750+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 22:30:16.922645+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 22:30:22.075385+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "probe_concern", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-08 22:30:27.555084+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-08 22:30:48.577046+00:00 {"intent": "answer", "turn_id": 5, "revision": 9, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-08 22:30:55.746752+00:00 {"intent": "answer", "turn_id": 6, "revision": 11, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-08 22:31:12.343371+00:00 {"intent": "answer", "turn_id": 7, "revision": 14, "answer_slot": "plans", "skip_planner": true, "utterance_id": "u-6"}
- #CALL_ENDED 9 2026-09-08 22:31:26.814183+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-34e06dfc — 2026-09-08 22:32:30.830961+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Великолепное настроение.", "wellness": "Чувствую себя хорошо."}
observations: 7
- t3 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t4 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t4 [mood] Великолепное настроение. | quote: Великолепное настроение.
- t5 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t5 [mood] Великолепное настроение. | quote: Великолепное настроение.
- t6 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t6 [mood] Великолепное настроение. | quote: Великолепное настроение.
key events: 8
- #CALL_STARTED 1 2026-09-08 22:31:42.235671+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 22:31:42.258482+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 22:31:50.107680+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 4 2026-09-08 22:32:03.320877+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-08 22:32:12.832101+00:00 {"intent": "unclear", "turn_id": 4, "revision": 7, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 6 2026-09-08 22:32:15.837762+00:00 {"intent": "backchannel", "turn_id": 5, "revision": 9, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 7 2026-09-08 22:32:25.174543+00:00 {"intent": "unclear", "turn_id": 6, "revision": 9, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-6"}
- #CALL_ENDED 8 2026-09-08 22:32:30.835531+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-592f4ea0 — 2026-09-08 22:48:16.378444+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно.", "plans": "Сегодня планов нету. Отдыха...
observations: 8
- t3 [wellness] Плохо спал. | quote: Плохо спал.
- t4 [wellness] Плохо спал. | quote: Плохо спал.
- t5 [wellness] Плохо спал. | quote: Плохо спал.
- t6 [wellness] Плохо спал. | quote: Плохо спал.
- t6 [mood] Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно. | quote: Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно.
- t7 [wellness] Плохо спал. | quote: Плохо спал.
- t7 [mood] Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно. | quote: Настроение хорошее сегодня. Чувствую себя великолепно. Но вот это вот, то, что живот болит, не очень, конечно.
- t7 [sleep] Спал в целом нормально. | quote: Спал в целом нормально.
key events: 9
- #CALL_STARTED 1 2026-09-08 22:47:09.543240+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 22:47:09.570825+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 22:47:19.301300+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 4 2026-09-08 22:47:28.919175+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "probe_concern", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-08 22:47:36.246396+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 6 2026-09-08 22:47:48.585425+00:00 {"intent": "answer", "turn_id": 5, "revision": 9, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 7 2026-09-08 22:48:03.372340+00:00 {"intent": "answer", "turn_id": 6, "revision": 11, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 8 2026-09-08 22:48:12.227423+00:00 {"intent": "answer", "turn_id": 7, "revision": 14, "answer_slot": "plans", "skip_planner": true, "utterance_id": "u-7"}
- #CALL_ENDED 9 2026-09-08 22:48:16.381788+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-641ab72d — 2026-09-08 22:56:30.956808+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое.", "wellness": "Чувствую себя плохо."}
observations: 5
- t3 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t4 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t5 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t6 [wellness] Чувствую себя плохо. | quote: Чувствую себя плохо.
- t6 [mood] Плохое. | quote: Плохое.
key events: 8
- #CALL_STARTED 1 2026-09-08 22:55:00.274129+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-08 22:55:00.299127+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-08 22:55:10.566866+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-08 22:55:19.137826+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "probe_concern", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-08 22:55:26.497341+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-08 22:55:36.158635+00:00 {"intent": "answer", "turn_id": 5, "revision": 9, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-08 22:55:56.615795+00:00 {"intent": "answer", "turn_id": 6, "revision": 11, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #CALL_ENDED 8 2026-09-08 22:56:30.961271+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c33d32e8 — 2026-09-09 00:03:06.978891+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-09 00:02:43.189737+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 00:02:43.221934+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-09 00:02:51.466812+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #CALL_ENDED 5 2026-09-09 00:03:06.984983+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d8838b70 — 2026-09-09 00:03:28.901891+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Хорошая.", "plans": "Планов нет на сегодня.", "sleep": "Нормально пойдёт.", "wellness": "Пять."}
observations: 6
- t3 [wellness] Пять. | quote: Пять.
- t4 [wellness] Пять. | quote: Пять.
- t4 [mood] Хорошая. | quote: Хорошая.
- t5 [wellness] Пять. | quote: Пять.
- t5 [mood] Хорошая. | quote: Хорошая.
- t5 [sleep] Нормально пойдёт. | quote: Нормально пойдёт.
key events: 7
- #CALL_STARTED 1 2026-09-09 00:02:44.676180+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 00:02:44.700798+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 00:03:07.365795+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-09 00:03:14.433813+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-09 00:03:19.742152+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-09 00:03:25.493072+00:00 {"intent": "answer", "turn_id": 5, "revision": 10, "answer_slot": "plans", "skip_planner": true, "utterance_id": "u-4"}
- #CALL_ENDED 7 2026-09-09 00:03:28.905945+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f9f41447 — 2026-09-09 00:05:16.123812+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Плохое.", "wellness": "Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела."}
observations: 2
- t3 [wellness] Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела. | quote: Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела.
- t4 [wellness] Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела. | quote: Привет. Чувствую себя очень плохо, голова болит. Вот в 4:00 утра голова заболела.
key events: 6
- #CALL_STARTED 1 2026-09-09 00:04:48.983142+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 00:04:49.017946+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 00:05:01.338423+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 4 2026-09-09 00:05:06.731000+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-09 00:05:13.548288+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-4"}
- #CALL_ENDED 6 2026-09-09 00:05:16.126248+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a80ee60f — 2026-09-09 00:10:14.044071+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "голова болит и тошнит меня"}
observations: 2
- t7 [wellness] голова болит и тошнит меня | quote: голова болит и тошнит меня
- t8 [wellness] голова болит и тошнит меня | quote: голова болит и тошнит меня
key events: 10
- #CALL_STARTED 1 2026-09-09 00:08:34.996180+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 00:08:35.024547+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 00:08:48.574347+00:00 {"intent": "unclear", "turn_id": 2, "revision": 3, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-09 00:08:58.876996+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-09 00:09:13.333777+00:00 {"intent": "unclear", "turn_id": 4, "revision": 7, "answer_slot": "topic_headache", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-09 00:09:17.312368+00:00 {"intent": "backchannel", "turn_id": 5, "revision": 9, "answer_slot": "topic_headache", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-09 00:09:26.908818+00:00 {"intent": "answer", "turn_id": 6, "revision": 10, "answer_slot": "topic_headache", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-09 00:09:42.979270+00:00 {"intent": "answer", "turn_id": 7, "revision": 12, "answer_slot": "topic_abdominal_pain", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-09 00:09:52.418900+00:00 {"intent": "answer", "turn_id": 8, "revision": 13, "answer_slot": "topic_abdominal_pain", "skip_planner": true, "utterance_id": "u-7"}
- #CALL_ENDED 10 2026-09-09 00:10:14.047326+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## pg-a33099787e40 — 2026-09-09 01:35:13.819081+00:00 (fsm=DAILY_CHECK, termination=None)

family=fam-pg-test ended=False
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-09 01:35:13.773445+00:00 {"family_id": "fam-pg-test"}
- #PLANNER_DECISION 2 2026-09-09 01:35:13.785107+00:00 {"intent": "wait_for_continuation", "turn_id": 2, "user_act": "backchannel", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utt...
- #PLANNER_DECISION 3 2026-09-09 01:35:13.804006+00:00 {"intent": "check_wellness", "turn_id": 3, "user_act": "answer", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id": ...

## pg-idem-989baebc34f8 — 2026-09-09 01:35:13.930337+00:00 (fsm=DAILY_CHECK, termination=None)

family=fam-pg-idem ended=False
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-09 01:35:13.859943+00:00 {"family_id": "fam-pg-idem"}
- #PLANNER_DECISION 2 2026-09-09 01:35:13.865772+00:00 {"intent": "wait_for_continuation", "turn_id": 2, "user_act": "backchannel", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utt...
- #PLANNER_DECISION 3 2026-09-09 01:35:13.881665+00:00 {"intent": "check_wellness", "turn_id": 3, "user_act": "answer", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id": ...
- #PLANNER_DECISION 4 2026-09-09 01:35:13.898452+00:00 {"intent": "check_wellness", "turn_id": 4, "user_act": "unclear", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id":...
- #PLANNER_DECISION 5 2026-09-09 01:35:13.916276+00:00 {"intent": "repair_repeat", "turn_id": 5, "user_act": "repeat", "fsm_state": "DAILY_CHECK", "pending_slot": "wellness", "skip_planner": false, "utterance_id": "...

## pg-3778ef2f9083 — 2026-09-09 01:35:18.592443+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-test ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-09 01:35:18.527947+00:00 {"family_id": "fam-pg-test"}
- #PLANNER_DECISION 2 2026-09-09 01:35:18.535590+00:00 {"intent": "confirm_consent", "turn_id": 2, "user_act": "answer", "fsm_state": "CHECK_CONSENT", "pending_slot": null, "skip_planner": false, "utterance_id": "u-...
- #PLANNER_DECISION 3 2026-09-09 01:35:18.557403+00:00 {"intent": "consent_declined_final", "turn_id": 3, "user_act": "answer", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "skip_planner": false, "utte...
- #CALL_ENDED 4 2026-09-09 01:35:18.597014+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## pg-idem-209887c7bf16 — 2026-09-09 01:35:18.684535+00:00 (fsm=FINAL_CLASSIFICATION, termination=CONSENT_DECLINED)

family=fam-pg-idem ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-09 01:35:18.634248+00:00 {"family_id": "fam-pg-idem"}
- #PLANNER_DECISION 2 2026-09-09 01:35:18.640682+00:00 {"intent": "confirm_consent", "turn_id": 2, "user_act": "answer", "fsm_state": "CHECK_CONSENT", "pending_slot": null, "skip_planner": false, "utterance_id": "u-...
- #PLANNER_DECISION 3 2026-09-09 01:35:18.656130+00:00 {"intent": "consent_declined_final", "turn_id": 3, "user_act": "answer", "fsm_state": "FINAL_CLASSIFICATION", "pending_slot": null, "skip_planner": false, "utte...
- #CALL_ENDED 4 2026-09-09 01:35:18.686663+00:00 {"partial": true, "termination_reason": "CONSENT_DECLINED"}

## fs-72b01e3c — 2026-09-09 02:07:09.961455+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-09 02:06:33.693967+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 02:06:33.739389+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #CALL_ENDED 3 2026-09-09 02:07:09.966014+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e3e257e1 — 2026-09-09 02:38:25.708505+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Хуёвое у меня настроение, вера, хуёвое.", "wellness": "Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю."}
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
key events: 10
- #CALL_STARTED 1 2026-09-09 02:36:27.180643+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 02:36:27.208914+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 02:36:39.086059+00:00 {"intent": "answer", "turn_id": 2, "revision": 3, "rich_turn": false, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-09 02:36:48.184611+00:00 {"intent": "answer", "turn_id": 3, "revision": 5, "rich_turn": false, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-09 02:37:05.691098+00:00 {"intent": "answer", "turn_id": 4, "revision": 7, "rich_turn": true, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-09 02:37:22.178444+00:00 {"intent": "question", "turn_id": 5, "revision": 10, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-09 02:37:40.864360+00:00 {"intent": "answer", "turn_id": 6, "revision": 13, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-09 02:37:56.808756+00:00 {"intent": "answer", "turn_id": 7, "revision": 16, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-09 02:38:12.817384+00:00 {"intent": "question", "turn_id": 8, "revision": 20, "rich_turn": true, "answer_slot": "episode_ep-ee8ba1cb_onset", "skip_planner": true, "utterance_id": "u-7"}
- #CALL_ENDED 10 2026-09-09 02:38:25.711613+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ad907a00 — 2026-09-09 19:37:57.704656+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 12
- #CALL_STARTED 1 2026-09-09 19:35:49.457703+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 19:35:49.482410+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 19:36:01.097295+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 4 2026-09-09 19:36:04.301563+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "episode_headache_onset", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-09 19:36:13.639592+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 6 2026-09-09 19:36:20.685504+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "episode_ep-ce382d5a_onset", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 7 2026-09-09 19:36:26.175903+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "episode_ep-ce382d5a_onset", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 8 2026-09-09 19:36:53.165999+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "episode_ep-c487a111_onset", "skip_planner": true, "utterance_id": "u-9"}
- #ENGINE_DECISION 9 2026-09-09 19:37:24.266605+00:00 {"intent": "answer", "turn_id": 8, "revision": 22, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-12"}
- #ENGINE_DECISION 10 2026-09-09 19:37:43.250262+00:00 {"intent": "answer", "turn_id": 9, "revision": 24, "rich_turn": true, "answer_slot": "episode_ep-c487a111_onset", "skip_planner": true, "utterance_id": "u-14"}
- #ENGINE_DECISION 11 2026-09-09 19:37:54.750502+00:00 {"intent": "answer", "turn_id": 10, "revision": 25, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-15"}
- #CALL_ENDED 12 2026-09-09 19:37:57.711267+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-78aadac2 — 2026-09-09 20:09:30.658154+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-09 20:09:14.589228+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 20:09:14.611695+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 20:09:19.790946+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-09 20:09:21.427730+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #CALL_ENDED 5 2026-09-09 20:09:30.661834+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-77afbbf1 — 2026-09-09 20:10:10.381892+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
observations: 1
- t3 [wellness] negative | quote: negative
key events: 5
- #CALL_STARTED 1 2026-09-09 20:09:36.457221+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 20:09:36.482380+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 20:09:48.965497+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-09 20:09:55.097615+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-2"}
- #CALL_ENDED 5 2026-09-09 20:10:10.384214+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-9032fcf4 — 2026-09-09 22:02:37.914340+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
observations: 3
- t3 [wellness] negative | quote: negative
- t4 [wellness] negative | quote: negative
- t5 [wellness] negative | quote: negative
key events: 7
- #CALL_STARTED 1 2026-09-09 22:01:56.586052+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-09 22:01:56.608587+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-09 22:02:09.187301+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-09 22:02:15.400055+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-09 22:02:24.081149+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_current_status", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-09 22:02:31.321499+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-4"}
- #CALL_ENDED 7 2026-09-09 22:02:37.919479+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-996c3fa1 — 2026-09-10 11:40:02.918657+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-10 11:39:19.569407+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 11:39:19.588908+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-10 11:39:32.145888+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #CALL_ENDED 4 2026-09-10 11:40:02.921445+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c83012aa — 2026-09-10 12:08:59.381357+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "positive"}
observations: 1
- t3 [mood] positive | quote: positive
key events: 5
- #CALL_STARTED 1 2026-09-10 12:08:34.555563+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 12:08:34.583480+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-10 12:08:46.127396+00:00 {"intent": "answer", "turn_id": 2, "revision": 6, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 4 2026-09-10 12:08:56.309483+00:00 {"intent": "answer", "turn_id": 3, "revision": 10, "rich_turn": true, "answer_slot": null, "skip_planner": true, "utterance_id": "u-3"}
- #CALL_ENDED 5 2026-09-10 12:08:59.383543+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f534c2e6 — 2026-09-10 12:22:44.249398+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "positive", "wellness": "positive"}
observations: 4
- t3 [wellness] positive | quote: positive
- t3 [mood] positive | quote: positive
- t4 [wellness] positive | quote: positive
- t4 [mood] positive | quote: positive
key events: 6
- #CALL_STARTED 1 2026-09-10 12:22:10.526806+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 12:22:10.552250+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-10 12:22:20.932609+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 4 2026-09-10 12:22:32.408649+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-10 12:22:40.447464+00:00 {"intent": "answer", "turn_id": 4, "revision": 12, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #CALL_ENDED 6 2026-09-10 12:22:44.251391+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-587e6306 — 2026-09-10 12:37:47.398893+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-10 12:37:43.553314+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 12:37:43.588887+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #CALL_ENDED 3 2026-09-10 12:37:47.401561+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0fc0055e — 2026-09-10 12:44:25.192048+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-10 12:44:21.317226+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 12:44:21.341990+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #CALL_ENDED 3 2026-09-10 12:44:25.194277+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0c4eb96b — 2026-09-10 12:45:25.462911+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 3
- #CALL_STARTED 1 2026-09-10 12:45:22.746051+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 12:45:22.769314+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #CALL_ENDED 3 2026-09-10 12:45:25.464909+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1f6d3000 — 2026-09-10 12:52:12.574254+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
observations: 4
- t3 [wellness] negative | quote: negative
- t4 [wellness] negative | quote: negative
- t5 [wellness] negative | quote: negative
- t6 [wellness] negative | quote: negative
key events: 8
- #CALL_STARTED 1 2026-09-10 12:51:19.856162+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 12:51:19.880690+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-10 12:51:34.982803+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-10 12:51:45.348427+00:00 {"intent": "answer", "turn_id": 3, "revision": 9, "rich_turn": true, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-10 12:51:55.052793+00:00 {"intent": "answer", "turn_id": 4, "revision": 13, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-10 12:52:03.347218+00:00 {"intent": "answer", "turn_id": 5, "revision": 16, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-10 12:52:07.815923+00:00 {"intent": "answer", "turn_id": 6, "revision": 20, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #CALL_ENDED 8 2026-09-10 12:52:12.576702+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-69673837 — 2026-09-10 15:38:50.162341+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "positive"}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-10 15:38:35.881648+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 15:38:35.907532+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-10 15:38:42.041458+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-10 15:38:43.896759+00:00 {"intent": "answer", "turn_id": 3, "revision": 9, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #CALL_ENDED 5 2026-09-10 15:38:50.168219+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-2b372628 — 2026-09-10 15:39:56.625423+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено болит."}
observations: 5
- t3 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t4 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t5 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t6 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
- t7 [wellness] Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол | quote: Привет. Чувствую себя хорошо, даже я б сказал бы отлично, но тут такая проблема: у меня болит сильно голова и колено бол
key events: 9
- #CALL_STARTED 1 2026-09-10 15:38:53.424484+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-10 15:38:53.449844+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-10 15:39:10.569034+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-10 15:39:16.021936+00:00 {"intent": "backchannel", "turn_id": 3, "revision": 6, "rich_turn": true, "answer_slot": "episode_compound_temporal_current", "skip_planner": true, "utterance_i...
- #ENGINE_DECISION 5 2026-09-10 15:39:24.164149+00:00 {"intent": "answer", "turn_id": 4, "revision": 8, "rich_turn": true, "answer_slot": "episode_compound_temporal_current", "skip_planner": true, "utterance_id": "...
- #ENGINE_DECISION 6 2026-09-10 15:39:31.055123+00:00 {"intent": "answer", "turn_id": 5, "revision": 11, "rich_turn": true, "answer_slot": "episode_ep-d6bcb5b1_onset", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-10 15:39:45.696032+00:00 {"intent": "answer", "turn_id": 6, "revision": 15, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-10 15:39:53.564242+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-6"}
- #CALL_ENDED 9 2026-09-10 15:39:56.630904+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c49395f7 — 2026-09-11 00:44:29.230265+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит."}
observations: 2
- t3 [wellness] Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит. | quote: Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит.
- t4 [wellness] Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит. | quote: Привет. Чувствую себя плохо. Голова болит, колено болит, плохое самочувствие, почки болят, спина болит.
key events: 6
- #CALL_STARTED 1 2026-09-11 00:43:46.394769+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 00:43:46.423340+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-11 00:44:04.664232+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-11 00:44:18.282647+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "episode_compound_temporal_current", "skip_planner": true, "utterance_id": "...
- #ENGINE_DECISION 5 2026-09-11 00:44:26.591107+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-4"}
- #CALL_ENDED 6 2026-09-11 00:44:29.238940+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

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
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-11 17:30:10.606014+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 17:30:10.634152+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-11 17:30:18.926453+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-11 17:30:19.384485+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-11 17:30:19.414375+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

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
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-11 17:33:49.644984+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 17:33:49.666807+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-11 17:33:57.672531+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-11 17:33:57.768704+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-11 17:33:57.794182+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## call-19e219e2b1e8 — 2026-09-11 17:35:24.734437+00:00 (fsm=CALL_START, termination=None)

family=fam-phone-accept ended=False
facts={}
observations: 0
key events: 0

## fs-bf61f52b — 2026-09-11 19:38:31.030485+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Да"}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-11 19:38:18.092915+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 19:38:18.128964+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-11 19:38:24.487600+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-11 19:38:31.005255+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-11 19:38:31.035686+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-223c5ba1 — 2026-09-11 21:14:45.227559+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-11 21:14:17.026124+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 21:14:17.065388+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-11 21:14:29.351942+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-11 21:14:45.172766+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-11 21:14:45.231655+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fab680cb — 2026-09-11 21:15:42.922162+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя... Ну, сам себя чувствую хорошо. До этого болела у меня голова, и было тошното, плохое самочувствие."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-11 21:15:12.305988+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 21:15:12.371519+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-11 21:15:29.628647+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-11 21:15:42.874814+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-11 21:15:42.925246+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-2ba16ccd — 2026-09-11 21:18:11.404647+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-11 21:18:01.391604+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 21:18:01.409809+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-11 21:18:11.368536+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-11 21:18:11.410218+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-1839074e — 2026-09-11 21:18:11.959264+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо."}
observations: 3
- t3 [wellness] Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо. | quote: Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо.
- t4 [wellness] Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо. | quote: Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо.
- t5 [wellness] Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо. | quote: Привет. А-а, смотри, э-э, голова болела сегодня. Сейчас вроде чувствую себя хорошо.
key events: 8
- #CALL_STARTED 1 2026-09-11 21:17:21.164563+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 21:17:21.193056+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-11 21:17:35.711396+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-11 21:17:44.124792+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "episode_headache_current", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-11 21:17:59.131595+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-11 21:18:10.029449+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "episode_ep-43195fae_onset", "skip_planner": true, "utterance_id": "u-4"}
- #ACTION_POLICY_SHADOW_HEALTH 7 2026-09-11 21:18:11.932219+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 8 2026-09-11 21:18:11.962428+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-8489e41a — 2026-09-11 22:55:40.637045+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-11 22:55:12.429425+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 22:55:12.457358+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-11 22:55:25.180758+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-11 22:55:40.610399+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-11 22:55:40.640742+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-801bd4fc — 2026-09-11 22:57:07.212699+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-11 22:56:39.370663+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 22:56:39.391543+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-11 22:56:51.766245+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-11 22:57:07.188583+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-11 22:57:07.215200+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-9621515c — 2026-09-11 23:00:44.013626+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё."}
observations: 3
- t3 [wellness] Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё. | quote: Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё.
- t4 [wellness] Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё. | quote: Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё.
- t5 [wellness] Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё. | quote: Привет. Чувствую себя плохо. Головная боль тошнит. Зубная боль ещё.
key events: 8
- #CALL_STARTED 1 2026-09-11 22:59:35.687939+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-11 22:59:35.716123+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-11 22:59:54.030111+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-11 23:00:09.896789+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-11 23:00:19.882582+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_ep-456dee46_needs_help", "skip_planner": true, "utterance_id": "u-...
- #ENGINE_DECISION 6 2026-09-11 23:00:33.462795+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ACTION_POLICY_SHADOW_HEALTH 7 2026-09-11 23:00:43.989242+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 8 2026-09-11 23:00:44.017310+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-4b1c368e — 2026-09-12 01:22:49.344832+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-12 01:22:44.407596+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-12 01:22:44.429308+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-12 01:22:49.319218+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-12 01:22:49.348972+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-213aae70 — 2026-09-12 01:23:55.042264+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Привет, чувствую себя очень плохо, болит голова и меня тошнит."}
observations: 2
- t3 [wellness] Привет, чувствую себя очень плохо, болит голова и меня тошнит. | quote: Привет, чувствую себя очень плохо, болит голова и меня тошнит.
- t4 [wellness] Привет, чувствую себя очень плохо, болит голова и меня тошнит. | quote: Привет, чувствую себя очень плохо, болит голова и меня тошнит.
key events: 7
- #CALL_STARTED 1 2026-09-12 01:22:54.573159+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-12 01:22:54.595640+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-12 01:23:06.142220+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-12 01:23:25.740025+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-12 01:23:43.394335+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-3"}
- #ACTION_POLICY_SHADOW_HEALTH 6 2026-09-12 01:23:55.007529+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 7 2026-09-12 01:23:55.046527+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-5b507969 — 2026-09-12 01:28:04.927280+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Нет, отстань."}
observations: 3
- t4 [wellness] Нет, отстань. | quote: Нет, отстань.
- t5 [wellness] Нет, отстань. | quote: Нет, отстань.
- t6 [wellness] Нет, отстань. | quote: Нет, отстань.
key events: 9
- #CALL_STARTED 1 2026-09-12 01:27:24.137221+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-12 01:27:24.163418+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-12 01:27:36.542951+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ENGINE_DECISION 4 2026-09-12 01:27:46.174582+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 5 2026-09-12 01:27:54.415650+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 6 2026-09-12 01:28:00.258691+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 7 2026-09-12 01:28:04.880652+00:00 {"intent": "answer", "turn_id": 6, "revision": 15, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-12 01:28:04.908208+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-12 01:28:04.928900+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-1d991b27 — 2026-09-12 01:34:32.377800+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя хорошо."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-12 01:34:17.217618+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-12 01:34:17.246102+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-12 01:34:27.857775+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-12 01:34:32.356760+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-12 01:34:32.379672+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f3b28dd3 — 2026-09-12 01:36:26.613000+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Уже по-другому говорит. Чувствуй себя хорошо."}
observations: 2
- t3 [wellness] Уже по-другому говорит. Чувствуй себя хорошо. | quote: Уже по-другому говорит. Чувствуй себя хорошо.
- t4 [wellness] Уже по-другому говорит. Чувствуй себя хорошо. | quote: Уже по-другому говорит. Чувствуй себя хорошо.
key events: 7
- #CALL_STARTED 1 2026-09-12 01:35:41.871085+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-12 01:35:41.892842+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-12 01:35:51.465435+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-12 01:36:05.002232+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-12 01:36:18.672225+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "episode_ep-59af93e7_needs_help", "skip_planner": true, "utterance_id": "u-...
- #ACTION_POLICY_SHADOW_HEALTH 6 2026-09-12 01:36:26.582253+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 7 2026-09-12 01:36:26.615857+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-965f5b0b — 2026-09-12 01:42:10.943602+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-12 01:42:05.958593+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-12 01:42:05.978545+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-12 01:42:10.920189+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-12 01:42:10.946036+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-54c67d76 — 2026-09-13 14:14:23.686505+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-13 14:14:06.121601+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 14:14:06.141737+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 14:14:17.383143+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-13 14:14:23.663826+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-13 14:14:23.690380+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-87312170 — 2026-09-13 14:15:10.367933+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
observations: 3
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
key events: 8
- #CALL_STARTED 1 2026-09-13 14:14:29.218873+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 14:14:29.239490+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 14:14:36.712893+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 14:14:49.131732+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 14:14:58.532679+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_ep-ec29e631_onset", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 14:15:06.013198+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "episode_ep-ec29e631_onset", "skip_planner": true, "utterance_id": "u-4"}
- #ACTION_POLICY_SHADOW_HEALTH 7 2026-09-13 14:15:10.338312+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 8 2026-09-13 14:15:10.370076+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-c436546b — 2026-09-13 14:19:05.862136+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
observations: 4
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
key events: 9
- #CALL_STARTED 1 2026-09-13 14:18:24.200622+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 14:18:24.222762+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 14:18:31.735851+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 14:18:42.019654+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 14:18:51.825342+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_ep-a6caa19e_onset", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 14:19:01.225469+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "episode_ep-a6caa19e_onset", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 14:19:05.825514+00:00 {"intent": "answer", "turn_id": 6, "revision": 15, "rich_turn": true, "answer_slot": null, "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-13 14:19:05.845001+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-13 14:19:05.864196+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d42264b9 — 2026-09-13 14:34:37.643263+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
observations: 4
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
key events: 9
- #CALL_STARTED 1 2026-09-13 14:33:46.198241+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 14:33:46.218808+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 14:33:53.963300+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 14:34:04.659832+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 14:34:15.294273+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_ep-1d7706e3_onset", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 14:34:22.540490+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "episode_ep-1d7706e3_current", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 14:34:35.802820+00:00 {"intent": "answer", "turn_id": 6, "revision": 18, "rich_turn": true, "answer_slot": null, "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-13 14:34:37.619600+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-13 14:34:37.645558+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a7bffaf1 — 2026-09-13 14:37:57.860539+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил."}
observations: 4
- t3 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
- t4 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
- t5 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
- t6 [wellness] Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил. | quote: Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас. Не, это хуйня, ты сразу всё спросил.
key events: 9
- #CALL_STARTED 1 2026-09-13 14:36:52.401139+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 14:36:52.422075+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 14:37:06.435735+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 14:37:21.293698+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 14:37:32.739041+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 14:37:44.586621+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 14:37:53.489780+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-13 14:37:57.832076+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-13 14:37:57.863438+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-41e2a57b — 2026-09-13 14:38:54.466692+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Пло."}
observations: 4
- t3 [wellness] Пло. | quote: Пло.
- t4 [wellness] Пло. | quote: Пло.
- t5 [wellness] Пло. | quote: Пло.
- t6 [wellness] Пло. | quote: Пло.
key events: 9
- #CALL_STARTED 1 2026-09-13 14:38:08.091455+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 14:38:08.111755+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 14:38:15.289265+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 14:38:28.155376+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 14:38:39.167240+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_ep-f913da5a_onset", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 14:38:47.618275+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "episode_ep-f913da5a_onset", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 14:38:51.582870+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-13 14:38:54.444850+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-13 14:38:54.468657+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0843128c — 2026-09-13 14:51:48.810701+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "negative", "plans": "У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце. У меня болит глаз сегодня, забыла покаплять в глаза...
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
key events: 11
- #CALL_STARTED 1 2026-09-13 14:50:29.472669+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 14:50:29.492898+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 14:50:38.731622+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 14:51:06.346151+00:00 {"intent": "answer", "turn_id": 3, "revision": 9, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 14:51:14.773094+00:00 {"intent": "answer", "turn_id": 4, "revision": 12, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 14:51:21.805944+00:00 {"intent": "answer", "turn_id": 5, "revision": 15, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 14:51:31.004932+00:00 {"intent": "answer", "turn_id": 6, "revision": 18, "rich_turn": true, "answer_slot": "episode_ep-ec21474c_onset", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-13 14:51:38.011903+00:00 {"intent": "answer", "turn_id": 7, "revision": 21, "rich_turn": true, "answer_slot": "episode_ep-1ebeee4d_onset", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-13 14:51:45.389100+00:00 {"intent": "answer", "turn_id": 8, "revision": 25, "rich_turn": true, "answer_slot": "episode_ep-1ebeee4d_onset", "skip_planner": true, "utterance_id": "u-7"}
- #ACTION_POLICY_SHADOW_HEALTH 10 2026-09-13 14:51:48.790021+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 11 2026-09-13 14:51:48.812494+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-a8964347 — 2026-09-13 15:05:01.971058+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Я чувствую себя плохо, болит живот и головная боль в данный момент."}
observations: 2
- t3 [wellness] Я чувствую себя плохо, болит живот и головная боль в данный момент. | quote: Я чувствую себя плохо, болит живот и головная боль в данный момент.
- t4 [wellness] Я чувствую себя плохо, болит живот и головная боль в данный момент. | quote: Я чувствую себя плохо, болит живот и головная боль в данный момент.
key events: 7
- #CALL_STARTED 1 2026-09-13 15:04:24.565242+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 15:04:24.591703+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 15:04:36.739681+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 15:04:50.701808+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "episode_ep-f869b3ee_onset", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 15:04:57.612785+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "episode_ep-f869b3ee_onset", "skip_planner": true, "utterance_id": "u-3"}
- #ACTION_POLICY_SHADOW_HEALTH 6 2026-09-13 15:05:01.942309+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 7 2026-09-13 15:05:01.973219+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0a6c52eb — 2026-09-13 23:28:36.646703+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-13 23:28:29.812004+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 23:28:29.833807+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-13 23:28:36.614947+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-13 23:28:36.648937+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-16d22975 — 2026-09-13 23:30:04.486519+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Триво.", "sleep": "Нет.", "wellness": "Хорошо."}
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
key events: 14
- #CALL_STARTED 1 2026-09-13 23:28:42.328364+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 23:28:42.348102+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 23:28:50.465368+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 23:28:57.742980+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 23:29:03.571706+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 23:29:10.472969+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 23:29:14.912098+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-13 23:29:31.539600+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-13 23:29:40.132236+00:00 {"intent": "answer", "turn_id": 8, "revision": 22, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-7"}
- #ENGINE_DECISION 10 2026-09-13 23:29:48.674105+00:00 {"intent": "answer", "turn_id": 9, "revision": 25, "rich_turn": true, "answer_slot": "episode_ep-f9541c16_onset", "skip_planner": true, "utterance_id": "u-8"}
- #ENGINE_DECISION 11 2026-09-13 23:29:55.930427+00:00 {"intent": "answer", "turn_id": 10, "revision": 28, "rich_turn": true, "answer_slot": "episode_ep-f9541c16_onset", "skip_planner": true, "utterance_id": "u-9"}
- #ENGINE_DECISION 12 2026-09-13 23:30:00.076523+00:00 {"intent": "answer", "turn_id": 11, "revision": 32, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-10"}
- #ACTION_POLICY_SHADOW_HEALTH 13 2026-09-13 23:30:04.459824+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 14 2026-09-13 23:30:04.490070+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-07ba9ace — 2026-09-13 23:41:56.385565+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
observations: 5
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
- t7 [wellness] Хорошо. | quote: Хорошо.
key events: 10
- #CALL_STARTED 1 2026-09-13 23:41:03.200209+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 23:41:03.223625+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 23:41:11.483840+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 23:41:18.332866+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 23:41:23.417831+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 23:41:31.418669+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 23:41:43.705110+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-13 23:41:52.881781+00:00 {"intent": "answer", "turn_id": 7, "revision": 20, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-6"}
- #ACTION_POLICY_SHADOW_HEALTH 9 2026-09-13 23:41:56.363275+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 10 2026-09-13 23:41:56.387843+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-07799215 — 2026-09-13 23:43:21.175729+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Настроение плохое беспокоит, что у меня голова болит.", "plans": "Пойдёт.", "wellness": "Чувствую себя хорошо. Ты, блядь, подвизы её."}
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
key events: 14
- #CALL_STARTED 1 2026-09-13 23:42:02.232589+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 23:42:02.252504+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 23:42:12.571669+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 23:42:20.509766+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 23:42:25.269850+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 23:42:33.669540+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 23:42:43.201239+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "episode_ep-dee1c9a0_onset", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-13 23:42:50.555316+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "episode_ep-dee1c9a0_onset", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-13 23:42:59.115834+00:00 {"intent": "answer", "turn_id": 8, "revision": 22, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-7"}
- #ENGINE_DECISION 10 2026-09-13 23:43:07.200533+00:00 {"intent": "answer", "turn_id": 9, "revision": 25, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-8"}
- #ENGINE_DECISION 11 2026-09-13 23:43:12.141267+00:00 {"intent": "answer", "turn_id": 10, "revision": 28, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-9"}
- #ENGINE_DECISION 12 2026-09-13 23:43:16.977330+00:00 {"intent": "answer", "turn_id": 11, "revision": 32, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-10"}
- #ACTION_POLICY_SHADOW_HEALTH 13 2026-09-13 23:43:21.144346+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 14 2026-09-13 23:43:21.178234+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fe48f985 — 2026-09-13 23:57:20.736441+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Нет, вроде бы хорошо, только чуть-чуть горло как будто приболело.", "wellness": "Хорошо."}
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
key events: 12
- #CALL_STARTED 1 2026-09-13 23:55:45.543459+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-13 23:55:45.566054+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-13 23:55:53.436173+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-13 23:55:59.449619+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-13 23:56:04.847269+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-13 23:56:12.325755+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-13 23:56:22.845352+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-13 23:56:35.633466+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "episode_ep-ecbd940c_intake", "skip_planner": true, "utterance_id": "u-7"}
- #ENGINE_DECISION 9 2026-09-13 23:56:48.621115+00:00 {"intent": "answer", "turn_id": 8, "revision": 22, "rich_turn": true, "answer_slot": "episode_ep-ecbd940c_barrier", "skip_planner": true, "utterance_id": "u-8"}
- #ENGINE_DECISION 10 2026-09-13 23:57:07.236153+00:00 {"intent": "answer", "turn_id": 9, "revision": 26, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-9"}
- #ACTION_POLICY_SHADOW_HEALTH 11 2026-09-13 23:57:20.705895+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 12 2026-09-13 23:57:20.739054+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-ec54e568 — 2026-09-14 00:00:56.500778+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "positive", "sleep": "Спал отлично.", "wellness": "Отлично."}
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
key events: 10
- #CALL_STARTED 1 2026-09-14 00:00:07.007906+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:00:07.033026+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:00:15.590175+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:00:22.074477+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:00:26.374126+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:00:32.749945+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:00:37.957748+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-14 00:00:48.182944+00:00 {"intent": "answer", "turn_id": 7, "revision": 21, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-6"}
- #ACTION_POLICY_SHADOW_HEALTH 9 2026-09-14 00:00:56.472537+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 10 2026-09-14 00:00:56.503959+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-5324e8b6 — 2026-09-14 00:01:34.323922+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "negative", "wellness": "Плохо."}
observations: 4
- t3 [wellness] Плохо. | quote: Плохо.
- t3 [mood] negative | quote: negative
- t4 [wellness] Плохо. | quote: Плохо.
- t4 [mood] negative | quote: negative
key events: 7
- #CALL_STARTED 1 2026-09-14 00:01:10.720264+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:01:10.741583+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:01:19.323895+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:01:26.964919+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:01:32.842885+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ACTION_POLICY_SHADOW_HEALTH 6 2026-09-14 00:01:34.299621+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 7 2026-09-14 00:01:34.326225+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-4579ea0d — 2026-09-14 00:02:44.159116+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Хорошо. Ой, блядь."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 00:02:32.667698+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:02:32.694250+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:02:41.851578+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-14 00:02:44.141748+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-14 00:02:44.160803+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-b1e84021 — 2026-09-14 00:03:34.012886+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Классно."}
observations: 4
- t3 [wellness] Классно. | quote: Классно.
- t4 [wellness] Классно. | quote: Классно.
- t5 [wellness] Классно. | quote: Классно.
- t6 [wellness] Классно. | quote: Классно.
key events: 9
- #CALL_STARTED 1 2026-09-14 00:02:47.337563+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:02:47.359102+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:02:54.941997+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:03:01.082036+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:03:10.978395+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:03:20.385728+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:03:27.036534+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-14 00:03:33.989707+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-14 00:03:34.016010+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-fc3909d6 — 2026-09-14 00:05:23.595851+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "negative", "sleep": "Спал.", "wellness": "Ужасно."}
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
key events: 9
- #CALL_STARTED 1 2026-09-14 00:04:40.540801+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:04:40.563432+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:04:48.036896+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:04:53.734153+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:04:59.543534+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:05:06.066492+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:05:16.596763+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-14 00:05:23.566244+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-14 00:05:23.597841+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d99db688 — 2026-09-14 00:22:58.874826+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Непонятно."}
observations: 4
- t3 [wellness] Непонятно. | quote: Непонятно.
- t4 [wellness] Непонятно. | quote: Непонятно.
- t5 [wellness] Непонятно. | quote: Непонятно.
- t6 [wellness] Непонятно. | quote: Непонятно.
key events: 9
- #CALL_STARTED 1 2026-09-14 00:22:04.773706+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:22:04.794582+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:22:14.463847+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:22:21.468366+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:22:26.406541+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:22:36.542307+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:22:48.326634+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "episode_ep-61492be2_severity", "skip_planner": true, "utterance_id": "u-5"...
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-14 00:22:58.845680+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-14 00:22:58.876997+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-b661257d — 2026-09-14 00:29:55.524688+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
observations: 0
key events: 6
- #CALL_STARTED 1 2026-09-14 00:29:33.332633+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:29:33.353129+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:29:40.701690+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #WAIT_EXPIRED 4 2026-09-14 00:29:51.163464+00:00 {"turn_id": 3, "wait_id": "wait-background_medication", "pending_slot": "background_medication"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 00:29:55.499624+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 00:29:55.527473+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-b7b2ba14 — 2026-09-14 00:30:30.126052+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-14 00:30:25.215470+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:30:25.241759+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-14 00:30:30.099241+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-14 00:30:30.128590+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-9a2396b3 — 2026-09-14 00:32:43.566287+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Хорошо."}
observations: 5
- t3 [wellness] Хорошо. | quote: Хорошо.
- t4 [wellness] Хорошо. | quote: Хорошо.
- t5 [wellness] Хорошо. | quote: Хорошо.
- t6 [wellness] Хорошо. | quote: Хорошо.
- t7 [wellness] Хорошо. | quote: Хорошо.
key events: 10
- #CALL_STARTED 1 2026-09-14 00:32:05.796543+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:32:05.819158+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:32:13.344261+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:32:23.555336+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:32:28.874557+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:32:31.824869+00:00 {"intent": "backchannel", "turn_id": 5, "revision": 12, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:32:37.940467+00:00 {"intent": "answer", "turn_id": 6, "revision": 14, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-14 00:32:40.879563+00:00 {"intent": "backchannel", "turn_id": 7, "revision": 16, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-6"}
- #ACTION_POLICY_SHADOW_HEALTH 9 2026-09-14 00:32:43.537116+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 10 2026-09-14 00:32:43.568534+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-fe57cba6 — 2026-09-14 00:55:47.905264+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"mood": "Ничего не тревожит.", "sleep": "Да, нормально спал.", "wellness": "Хорошо чувствую себя."}
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
key events: 13
- #CALL_STARTED 1 2026-09-14 00:54:10.595649+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:54:10.617479+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:54:19.884254+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:54:29.570945+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:54:35.593996+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:54:45.507460+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:54:52.885229+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-14 00:55:00.144269+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-14 00:55:11.658402+00:00 {"intent": "answer", "turn_id": 8, "revision": 22, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-7"}
- #ENGINE_DECISION 10 2026-09-14 00:55:29.041733+00:00 {"intent": "answer", "turn_id": 9, "revision": 25, "rich_turn": true, "answer_slot": "episode_ep-8eefcbab_onset", "skip_planner": true, "utterance_id": "u-8"}
- #ENGINE_DECISION 11 2026-09-14 00:55:36.541294+00:00 {"intent": "answer", "turn_id": 10, "revision": 29, "rich_turn": true, "answer_slot": "episode_headache_current", "skip_planner": true, "utterance_id": "u-9"}
- #ACTION_POLICY_SHADOW_HEALTH 12 2026-09-14 00:55:47.875539+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 13 2026-09-14 00:55:47.907673+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e2c73edf — 2026-09-14 00:57:07.801845+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"plans": "Дома что-то холодно, поэтому как будто чуть сонливость у меня небольшая. А так, в принципе, себя хорошо чувствую. Но ногу вот сегодня подвернуло, пот...
observations: 6
- t3 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t4 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t5 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t6 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t7 [wellness] Чувствую себя хорошо. | quote: Чувствую себя хорошо.
- t7 [plans] Дома что-то холодно, поэтому как будто чуть сонливость у меня небольшая. А так, в принципе, себя хорошо чувствую. Но ног | quote: Дома что-то холодно, поэтому как будто чуть сонливость у меня небольшая. А так, в принципе, себя хорошо чувствую. Но ног
key events: 10
- #CALL_STARTED 1 2026-09-14 00:55:51.741889+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:55:51.762037+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:56:00.583086+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:56:08.544119+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:56:15.043653+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:56:22.260381+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:56:44.230971+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-14 00:56:57.450171+00:00 {"intent": "answer", "turn_id": 7, "revision": 21, "rich_turn": true, "answer_slot": "episode_ep-277744af_severity", "skip_planner": true, "utterance_id": "u-6"...
- #ACTION_POLICY_SHADOW_HEALTH 9 2026-09-14 00:57:07.773226+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 10 2026-09-14 00:57:07.803813+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-780904ae — 2026-09-14 00:58:05.867419+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "negative", "sleep": "Не выспался.", "wellness": "Ужасно."}
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
key events: 10
- #CALL_STARTED 1 2026-09-14 00:57:11.498857+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:57:11.519648+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:57:19.024478+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:57:25.776306+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:57:31.014547+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 00:57:40.030203+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 00:57:46.223267+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-14 00:57:58.859433+00:00 {"intent": "answer", "turn_id": 7, "revision": 20, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-6"}
- #ACTION_POLICY_SHADOW_HEALTH 9 2026-09-14 00:58:05.837317+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 10 2026-09-14 00:58:05.870070+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-6298a1a3 — 2026-09-14 01:00:49.233888+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"plans": "Живот немного побаливал после еды, но сейчас нормально. Ел сегодня мало, аппетита особого не было. Водик пил вроде нормально, слабость небольшая есть...
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
key events: 10
- #CALL_STARTED 1 2026-09-14 00:59:12.426913+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 00:59:12.446985+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 00:59:27.385865+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 00:59:39.659141+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 00:59:51.711982+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 01:00:13.114175+00:00 {"intent": "answer", "turn_id": 5, "revision": 15, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 01:00:28.620405+00:00 {"intent": "answer", "turn_id": 6, "revision": 18, "rich_turn": true, "answer_slot": "episode_ep-5f1b4e44_current", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-14 01:00:36.257030+00:00 {"intent": "answer", "turn_id": 7, "revision": 22, "rich_turn": true, "answer_slot": "episode_ep-069c29f4_onset", "skip_planner": true, "utterance_id": "u-6"}
- #ACTION_POLICY_SHADOW_HEALTH 9 2026-09-14 01:00:49.201162+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 10 2026-09-14 01:00:49.236765+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0ed5232c — 2026-09-14 01:02:48.355041+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"sleep": "В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.", "wellness": "В целом нормально. Хотя, если честно, ночью спал бе...
observations: 8
- t3 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t3 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t4 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t4 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t5 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t5 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t6 [wellness] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
- t6 [sleep] В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался. | quote: В целом нормально. Хотя, если честно, ночью спал беспокойно и пару раз просыпался.
key events: 9
- #CALL_STARTED 1 2026-09-14 01:01:32.943303+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 01:01:32.964052+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 01:01:48.032537+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 01:01:59.788864+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-14 01:02:19.538412+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-14 01:02:27.132490+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-14 01:02:41.361726+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-6"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-14 01:02:48.325866+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-14 01:02:48.356715+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-35e0a389 — 2026-09-14 09:56:05.382160+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-14 09:56:00.382078+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 09:56:00.403421+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-14 09:56:05.361011+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-14 09:56:05.383931+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-10ca89ef — 2026-09-14 21:24:09.390130+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Ой, привет. Чувствую себя очень плохо. У меня голова болит и тошнотное состояние. Умираю, короче."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 21:23:45.801200+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 21:23:45.827133+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 21:24:02.414547+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-14 21:24:09.363737+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-14 21:24:09.392393+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-0828912d — 2026-09-14 21:24:34.316514+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет, я умираю."}
observations: 1
- t3 [wellness] Привет, я умираю. | quote: Привет, я умираю.
key events: 6
- #CALL_STARTED 1 2026-09-14 21:24:13.360138+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 21:24:13.381177+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 21:24:21.632413+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 21:24:27.063270+00:00 {"intent": "repair", "turn_id": 3, "revision": 6, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 21:24:34.289445+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 21:24:34.319113+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-92b2dd5a — 2026-09-14 23:14:45.895744+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:14:18.171920+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:14:18.195402+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:14:30.514936+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:14:45.873925+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:14:45.898030+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-d2e22096 — 2026-09-14 23:19:12.198606+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:18:44.402426+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:18:44.424396+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:18:56.803738+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:19:12.161765+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:19:12.201100+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f72ec306 — 2026-09-14 23:20:59.325236+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:20:31.564337+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:20:31.586736+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:20:43.920723+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:20:59.297557+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:20:59.327291+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-2f3363da — 2026-09-14 23:23:12.924211+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:22:45.162855+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:22:45.183747+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:22:57.535581+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:23:12.900541+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:23:12.926831+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-1b3b90bd — 2026-09-14 23:33:47.203344+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:33:19.388141+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:33:19.409036+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:33:31.773649+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:33:47.182050+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:33:47.204876+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-57aa6f3d — 2026-09-14 23:38:20.698845+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:37:52.898994+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:37:52.919814+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:38:05.305437+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:38:20.673294+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:38:20.702106+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f8ee43b1 — 2026-09-14 23:47:12.234052+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:46:44.431363+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:46:44.454318+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:46:56.816026+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:47:12.209762+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:47:12.236590+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f8fab6dc — 2026-09-14 23:47:30.509491+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:47:02.720675+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:47:02.741228+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:47:15.069366+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:47:30.492828+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:47:30.511302+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-44fd798f — 2026-09-14 23:50:19.788908+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:49:52.030521+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:49:52.056431+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:50:04.427633+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:50:19.765901+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:50:19.791841+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-2311dd4a — 2026-09-14 23:55:14.297687+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Чувствую себя великолепно."}
observations: 1
- t3 [wellness] Чувствую себя великолепно. | quote: Чувствую себя великолепно.
key events: 6
- #CALL_STARTED 1 2026-09-14 23:54:52.257324+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:54:52.278741+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-14 23:55:00.622700+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-14 23:55:11.364581+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-2"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:55:14.275989+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:55:14.299507+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ddae11a2 — 2026-09-14 23:57:26.126721+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:56:58.404128+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:56:58.424025+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:57:10.755328+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:57:26.098109+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:57:26.129433+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-e8e2400a — 2026-09-14 23:58:54.362693+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-14 23:58:26.639307+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-14 23:58:26.659729+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-14 23:58:38.992299+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-14 23:58:54.340848+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-14 23:58:54.365617+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-4f2694c3 — 2026-09-15 00:01:10.408959+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-15 00:00:42.511985+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 00:00:42.532713+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-15 00:00:54.889705+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": "wellness"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-15 00:01:10.386812+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-15 00:01:10.411415+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-ff2f66d2 — 2026-09-15 00:05:08.009581+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-15 00:05:03.093550+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 00:05:03.115773+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-15 00:05:07.987412+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-15 00:05:08.011256+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a1dca80c — 2026-09-15 01:46:25.718972+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"mood": "Я же говорю, чё-то и хорошо, и плохо мне.", "plans": "Пойдёт.", "sleep": "Пойдёт.", "wellness": "Да вроде бы и нормально чувствую, и в то же время пло...
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
key events: 11
- #CALL_STARTED 1 2026-09-15 01:45:05.417524+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 01:45:05.436524+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-15 01:45:22.496885+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-15 01:45:38.932211+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "background_nutrition", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-15 01:45:47.444756+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "background_medication", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 6 2026-09-15 01:45:56.727016+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "mood", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 7 2026-09-15 01:46:02.136276+00:00 {"intent": "answer", "turn_id": 6, "revision": 17, "rich_turn": true, "answer_slot": "sleep", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 8 2026-09-15 01:46:12.871263+00:00 {"intent": "answer", "turn_id": 7, "revision": 20, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-7"}
- #ENGINE_DECISION 9 2026-09-15 01:46:21.256766+00:00 {"intent": "answer", "turn_id": 8, "revision": 24, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-8"}
- #ACTION_POLICY_SHADOW_HEALTH 10 2026-09-15 01:46:25.683211+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 11 2026-09-15 01:46:25.721807+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-abffeb17 — 2026-09-15 01:58:00.186250+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Всё отвратительно, Вера."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-15 01:57:47.793953+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 01:57:47.818364+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-15 01:57:57.942394+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-15 01:58:00.167452+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-15 01:58:00.189033+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-e8164316 — 2026-09-15 02:05:43.037524+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя паршиво, плохо, отвратительно, дерьмово. Даже не передать словами."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-15 02:05:26.242747+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 02:05:26.268649+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-15 02:05:39.779131+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-15 02:05:43.007829+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-15 02:05:43.040523+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-d6e4dccb — 2026-09-15 02:18:51.877561+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Чувствуй себя плохо, отвратительно, вообще плохо ощущай себя."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-15 02:18:36.497630+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 02:18:36.522768+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-15 02:18:47.968903+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-15 02:18:51.846045+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-15 02:18:51.879821+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-70509d29 — 2026-09-15 13:07:25.655176+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Ой, чувствую себя очень плохо. Умираю. Такое состояние плохое у меня прям."}
observations: 1
- t3 [wellness] Ой, чувствую себя очень плохо. Умираю. Такое состояние плохое у меня прям. | quote: Ой, чувствую себя очень плохо. Умираю. Такое состояние плохое у меня прям.
key events: 6
- #CALL_STARTED 1 2026-09-15 13:06:52.113338+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 13:06:52.137193+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-15 13:07:04.514163+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-15 13:07:18.666311+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-15 13:07:25.627707+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-15 13:07:25.656905+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-39cb7575 — 2026-09-15 13:08:01.084770+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Ну, более-менее, так, нормально."}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-15 13:07:42.579113+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 13:07:42.601828+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-15 13:07:51.553317+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-15 13:08:01.056486+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-15 13:08:01.087336+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-4bb9ac4c — 2026-09-15 22:27:07.754180+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-15 22:27:02.374620+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 22:27:02.405444+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-15 22:27:07.723895+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-15 22:27:07.758631+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-f184b782 — 2026-09-15 22:27:13.152006+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-15 22:27:07.679128+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-15 22:27:07.712810+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-15 22:27:13.122438+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-15 22:27:13.154845+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-0035db6c — 2026-09-16 01:51:50.425141+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-16 01:51:30.886080+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-16 01:51:30.933488+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-16 01:51:47.192386+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ACTION_POLICY_SHADOW_HEALTH 4 2026-09-16 01:51:50.374326+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 5 2026-09-16 01:51:50.428389+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-7be7ccda — 2026-09-16 02:08:08.661281+00:00 (fsm=FINAL_CLASSIFICATION, termination=PARTIAL)

family=fam-voice ended=True
facts={"wellness": "Не очень."}
observations: 2
- t4 [wellness] Не очень. | quote: Не очень.
- t5 [wellness] Не очень. | quote: Не очень.
key events: 8
- #CALL_STARTED 1 2026-09-16 02:07:15.064610+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-16 02:07:15.086871+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-16 02:07:26.243309+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-16 02:07:41.523086+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 5 2026-09-16 02:07:50.861253+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 6 2026-09-16 02:08:01.597593+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "", "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 7 2026-09-16 02:08:08.621068+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 8 2026-09-16 02:08:08.665074+00:00 {"partial": true, "termination_reason": "PARTIAL"}

## fs-f702d83e — 2026-09-16 13:37:41.812392+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "negative"}
observations: 4
- t3 [wellness] negative | quote: negative
- t4 [wellness] negative | quote: negative
- t5 [wellness] negative | quote: negative
- t6 [wellness] negative | quote: negative
key events: 9
- #CALL_STARTED 1 2026-09-16 13:36:31.452436+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-16 13:36:31.481060+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-16 13:36:45.434337+00:00 {"intent": "answer", "turn_id": 2, "revision": 5, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-16 13:37:00.691373+00:00 {"intent": "answer", "turn_id": 3, "revision": 8, "rich_turn": true, "answer_slot": "probe_concern", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-16 13:37:10.551591+00:00 {"intent": "answer", "turn_id": 4, "revision": 11, "rich_turn": true, "answer_slot": "probe_duration", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-16 13:37:23.907986+00:00 {"intent": "answer", "turn_id": 5, "revision": 14, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-16 13:37:35.411118+00:00 {"intent": "answer", "turn_id": 6, "revision": 18, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ACTION_POLICY_SHADOW_HEALTH 8 2026-09-16 13:37:41.785593+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 9 2026-09-16 13:37:41.815151+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-a6628c67 — 2026-09-17 01:12:16.446942+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 6
- #CALL_STARTED 1 2026-09-17 01:11:20.810757+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-17 01:11:20.849178+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-17 01:11:36.062315+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-17 01:12:07.839926+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-3"}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-17 01:12:16.406040+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-17 01:12:16.461444+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-98a7de1b — 2026-09-17 01:20:35.092997+00:00 (fsm=FINAL_CLASSIFICATION, termination=COMPLETED)

family=fam-voice ended=True
facts={"plans": "Да, сижу дома, кушаю, вот, хорошо себя вроде чувствую, всё нормально."}
observations: 1
- t7 [plans] Да, сижу дома, кушаю, вот, хорошо себя вроде чувствую, всё нормально. | quote: Да, сижу дома, кушаю, вот, хорошо себя вроде чувствую, всё нормально.
key events: 10
- #CALL_STARTED 1 2026-09-17 01:19:32.753927+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-17 01:19:32.774104+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-17 01:19:41.455399+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-17 01:19:50.461164+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-17 01:19:59.181899+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-17 01:20:07.551016+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-17 01:20:22.241579+00:00 {"intent": "answer", "turn_id": 6, "revision": 18, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-17 01:20:31.428001+00:00 {"intent": "answer", "turn_id": 7, "revision": 22, "rich_turn": true, "answer_slot": null, "skip_planner": true, "utterance_id": "u-6"}
- #ACTION_POLICY_SHADOW_HEALTH 9 2026-09-17 01:20:35.059390+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 10 2026-09-17 01:20:35.098010+00:00 {"partial": true, "termination_reason": "COMPLETED"}

## fs-2bd8bf64 — 2026-09-17 22:41:49.448697+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "как себя чувствуешь"}
observations: 6
- t3 [wellness] negative | quote: negative
- t4 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t5 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t6 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t7 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
- t8 [wellness] Ну не знаю, то ли голова болит, то ли живот. | quote: Ну не знаю, то ли голова болит, то ли живот.
key events: 11
- #CALL_STARTED 1 2026-09-17 22:40:22.168991+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-17 22:40:22.197054+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-17 22:40:37.964323+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-17 22:40:45.342665+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-17 22:40:57.117285+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-17 22:41:07.885252+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-17 22:41:16.732006+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-17 22:41:27.465655+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "episode_ep-2643a479_onset", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-17 22:41:37.462808+00:00 {"intent": "answer", "turn_id": 8, "revision": 23, "rich_turn": true, "answer_slot": "episode_ep-2643a479_current", "skip_planner": true, "utterance_id": "u-7"}
- #ACTION_POLICY_SHADOW_HEALTH 10 2026-09-17 22:41:49.418736+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v8", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 11 2026-09-17 22:41:49.452630+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-c3cb344d — 2026-09-18 15:54:24.486498+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 4
- #CALL_STARTED 1 2026-09-18 15:54:19.507018+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-18 15:54:19.543336+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ACTION_POLICY_SHADOW_HEALTH 3 2026-09-18 15:54:24.456601+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v9", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 4 2026-09-18 15:54:24.492402+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-23d28835 — 2026-09-20 01:20:49.617186+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-20 01:20:18.108257+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-20 01:20:18.144973+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-20 01:20:30.864088+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": null}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-20 01:20:49.561914+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v9", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-20 01:20:49.625412+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-cbcd1f18 — 2026-09-20 01:21:00.780245+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-20 01:20:28.786246+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-20 01:20:28.808586+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-20 01:20:41.169332+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": null}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-20 01:21:00.706830+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v9", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-20 01:21:00.782843+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-723f04e0 — 2026-09-20 01:26:47.665696+00:00 (fsm=DAILY_CHECK, termination=DISCONNECTED)

family=fam-voice ended=True
facts={}
observations: 0
key events: 5
- #CALL_STARTED 1 2026-09-20 01:26:15.879986+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-20 01:26:15.939022+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #WAIT_EXPIRED 3 2026-09-20 01:26:28.526045+00:00 {"turn_id": 2, "wait_id": "wait-wellness", "pending_slot": null}
- #ACTION_POLICY_SHADOW_HEALTH 5 2026-09-20 01:26:47.621487+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v9", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 6 2026-09-20 01:26:47.668691+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}

## fs-338ee6ab — 2026-09-20 01:34:28.660818+00:00 (fsm=SUMMARY, termination=DISCONNECTED)

family=fam-voice ended=True
facts={"wellness": "Привет. Чувствую себя плохо."}
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
key events: 15
- #CALL_STARTED 1 2026-09-20 01:32:20.302888+00:00 {"family_id": "fam-voice"}
- #ENGINE_DECISION 2 2026-09-20 01:32:20.335268+00:00 {"intent": "opening_wellness", "turn_id": 1, "revision": 1}
- #ENGINE_DECISION 3 2026-09-20 01:32:29.849145+00:00 {"intent": "answer", "turn_id": 2, "revision": 4, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-1"}
- #ENGINE_DECISION 4 2026-09-20 01:32:41.042094+00:00 {"intent": "answer", "turn_id": 3, "revision": 7, "rich_turn": true, "answer_slot": "wellness", "skip_planner": true, "utterance_id": "u-2"}
- #ENGINE_DECISION 5 2026-09-20 01:32:57.943406+00:00 {"intent": "answer", "turn_id": 4, "revision": 10, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-3"}
- #ENGINE_DECISION 6 2026-09-20 01:33:09.082645+00:00 {"intent": "answer", "turn_id": 5, "revision": 13, "rich_turn": true, "answer_slot": "episode_headache_duration", "skip_planner": true, "utterance_id": "u-4"}
- #ENGINE_DECISION 7 2026-09-20 01:33:18.734654+00:00 {"intent": "answer", "turn_id": 6, "revision": 16, "rich_turn": true, "answer_slot": "episode_headache_severity", "skip_planner": true, "utterance_id": "u-5"}
- #ENGINE_DECISION 8 2026-09-20 01:33:28.218861+00:00 {"intent": "answer", "turn_id": 7, "revision": 19, "rich_turn": true, "answer_slot": "episode_ep-192e15fe_onset", "skip_planner": true, "utterance_id": "u-6"}
- #ENGINE_DECISION 9 2026-09-20 01:33:35.858577+00:00 {"intent": "answer", "turn_id": 8, "revision": 22, "rich_turn": true, "answer_slot": "episode_ep-192e15fe_onset", "skip_planner": true, "utterance_id": "u-7"}
- #ENGINE_DECISION 10 2026-09-20 01:33:42.183964+00:00 {"intent": "answer", "turn_id": 9, "revision": 25, "rich_turn": true, "answer_slot": "episode_ep-192e15fe_current", "skip_planner": true, "utterance_id": "u-8"}
- #ENGINE_DECISION 11 2026-09-20 01:33:48.742435+00:00 {"intent": "answer", "turn_id": 10, "revision": 28, "rich_turn": true, "answer_slot": "episode_ep-30ed93fb_onset", "skip_planner": true, "utterance_id": "u-9"}
- #ENGINE_DECISION 12 2026-09-20 01:33:59.689499+00:00 {"intent": "answer", "turn_id": 11, "revision": 31, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-10"}
- #ENGINE_DECISION 13 2026-09-20 01:34:12.723350+00:00 {"intent": "answer", "turn_id": 12, "revision": 35, "rich_turn": true, "answer_slot": "important_to_share", "skip_planner": true, "utterance_id": "u-11"}
- #ACTION_POLICY_SHADOW_HEALTH 14 2026-09-20 01:34:28.623491+00:00 {"retry_count": 0, "dropped_count": 0, "policy_version": "action-policy-phase1-v9", "schema_version": 1, "buffer_remaining": 0, "records_produced": 0, "telemetr...
- #CALL_ENDED 15 2026-09-20 01:34:28.665852+00:00 {"partial": true, "termination_reason": "DISCONNECTED"}
