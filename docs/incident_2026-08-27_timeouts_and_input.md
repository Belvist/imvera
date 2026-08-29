# Incident record 2026-08-27 — timeouts & "AI ignores user input"

## Symptom

1. **Service instability**: repeated timeouts and service restarts that make the
   telephony service flaky (SIP `408 Request Timeout` was seen on the caller
   side; server logs showed `OSError: [Errno 48] Address already in use`).
2. **Assistant ignores the user**: on the phone path the caller speaks but the
   assistant keeps generating her own replies and does not answer what was said.

## Evidence collected

* `telephony/*.supervisor.log` (archive): 62× `EADDRINUSE` (Port 9500/9600)
  per supervisor log — a child spawned over an already-listening service,
  died on bind, backed off, and was relaunched forever (**restart storm**).
* `telephony/core/orchestrator.py`: the empty-LLM-reply fallback guard was
  `if fb and reply and reply != fb` — an empty model reply (`reply == ""`)
  made the condition false, so the caller was handed **silence** exactly when
  the model produced nothing usable.
* `telephony/adapters/moss_tts.py`: hardcoded `timeout=600` for `/generate`
  and `/stream`; a wedged dependency froze a turn for up to 10 minutes.
* `telephony/tg/tg_server.py`: stream read timeout was `CONTROL_TIMEOUT*10`
  = 600 s.
* `telephony/moss_agent.lua`: endpointing assumed every WAV is 8 kHz mono
  (`dur = (size-44)/16000`); backgrounded `curl -m 300` could orphan a
  5-minute generation; dialog loop hard-capped at `for i = 1, 6`.
* Phone audio-path diagnostics (`[turn-audio]`, `_wav_diag`) now log the real
  WAV header (rate/channels/depth/energy) of every recorded chunk and the
  merged file sent to STT — so a live "he doesn't hear me" is attributable to
  empty chunks (no RTP), silent RTP, or a mixed-format concat.

## Root causes and fixes

| # | Root cause | Fix | File |
|---|-----------|-----|------|
| RC-1 | Supervisor restarts children blindly over occupied ports | ADOPT-OR-SPAWN: probe health; adopt a healthy existing service; refuse to spawn over a foreign occupied port; never kill adopted endpoints; status exposes `external` | `telephony/moss_supervisor.py` |
| RC-2 | 600 s TTS / gateway timeouts promoted a stalled dependency into a 10-min freeze | New env-overridable defaults: TTS gen 35 s, stream idle 20 s, stream total 60 s, cancel 3 s; gateway turn stream idle 30 s / total 60 s | `telephony/adapters/moss_tts.py`, `telephony/tg/tg_server.py` |
| RC-3 | Empty LLM reply = silence (fallback guard evaluated `reply` truthiness) | Guard is now `if fb and reply != fb` so an empty reply triggers the scripted fallback | `telephony/core/orchestrator.py` |
| RC-4 | Endpointing assumed 8 kHz mono; wrong duration on PCMU/PCMA/Opus | Duration reads the real `byteRate` from the WAV header (offset 28..31 LE), default 16000 | `telephony/moss_agent.lua` |
| RC-5 | Control/stream `curl -m 300` could hold a turn up to 5 min | Bounded to 60 s (incl. the backgrounded turn_stream so orphans self-terminate) | `telephony/moss_agent.lua` |
| RC-6 | Phone loop capped at 6 user turns (felt like scripted IVR) | Raised to 12, still bounded; real exits are hangup/`finished=true` | `telephony/moss_agent.lua` |

## Not changed here (needs live FreeSWITCH validation)

* True full-duplex / barge-in on the SIP path (Vera deafs during her own
  playback). `play_wav` still uses plain `playback`; `play_and_detect_speech`
  requires pocketsphinx/mrcp engines that are not present. Replacing the
  record/poll loop with a continuous `record`-while-playing design is a
  live-channel change and must be exercised against a real FS session before
  shipping.
* Per-call runtime metrics dashboards and network captures — the analysis
  sandbox has no Docker/tcpdump and no live FS; ports 8600/9400/9500/9600 had
  no listeners there. On the deployment host capture with:
  `tcpdump -i any -s0 -w calls.pcap 'tcp port 8600 or tcp port 9400 or tcp port 9500 or tcp port 9600'`.

## Test results

Full suite after the fix: **210 tests** (was 203), the only failing tests are
the two pre-existing failures unrelated to this change:

* `test_vc002_daemon_http.DaemonHttpTests.test_generate_with_reference`
  (daemon-HTTP, predates this work);
* `test_stt_confidence.BlankTurnDiagTests.test_retainible_under_env`
  (accumulated `blank_audio/*.wav` in the tmp dir across runs).

New regression coverage (`telephony/tests/test_telephony_hardening.py`, 7 tests
all green): bounded TTS/tg timeouts and env override; supervisor
adopt-already-healthy / spawn-when-free / refuse-over-foreign-port; empty
LLM reply now reaches the fallback.

## Regression procedure after deployment

1. Start the stack; confirm `[supervisor] ... started pid=` (spawn) or
   `adopting (...)` exactly once per service — no repeated `started` lines.
2. Place a call; expect a new `[turn-audio] N chunk(s): ...` and
   `[turn-audio] merged -> ...` line per user turn; verify rate/channels/energy.
3. Say something while Vera is speaking: today she finishes; the fix ensures
   your recorded chunk still reaches STT afterwards (no dropped tail).
4. Confirm no `Address already in use` pattern appears in
   `telephony/*.supervisor.log` after two supervisor restarts.