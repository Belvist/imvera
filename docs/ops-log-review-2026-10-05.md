# System log review (2026-10-05 ~01:50 MSK) — what each log says

Sources: `/tmp/voiseup-*.log` (bridge, STT x2, TTS x2, qwen),
`docker logs imvera-freeswitch / imvera-db` (24 h), 836 traces in
`.run/traces/`. Answers below quote the logs, not memory.

## Bridge (`voiseup-bridge2.log`)

- 3× HTTP 500 on `/health/ready`: `ValueError: invalid literal for
  int() with base 10: '9102,http:'` — a comma replica list passed whole
  into httpx. From the previous boot; current code splits replicas
  (`split_urls`) and live `/health/ready` returns 200 three times in a
  row. No fix needed, already deployed.
- Otherwise clean: recovery (spool replay, orphan sweep) ran, forensic
  lines per turn present. 46 'error' hits are almost all these 3 plus
  tracebacks of the same.

## STT (`voiseup-stt.log`, `voiseup-stt2.log`)

- 114 + similar `QueueFullError: inference queue full` → each becomes an
  HTTP 429 (failover code), never silence. This is load shedding by
  design, but the count says concurrency pressure exists: worth a
  capacity re-probe before raising caps, not a bug to patch.

## TTS (`voiseup-tts-silero.log`, `voiseup-tts2.log`)

- Qwen busy drops (`RemoteProtocolError` / `ConnectError` / `ReadTimeout`
  after 0–4 chunks) → explicit fallback to silero, loud log lines. Same
  single-batch root cause as journaled before: stagger warmups, retry
  before first chunk is already in.
- Both workers currently report the qwen base revision — fallbacks were
  transient, not stuck.

## Qwen server (`voiseup-qwen-tts.log`)

- Healthy: `RTF 0.362` on recent synthesis, Metal path, no errors.

## FreeSWITCH (24 h)

- 122 error lines, all one cosmetic source: `mod_signalwire.c` CA-cert
  noise every ~15 min (verto signalling, unrelated to our SIP/RTP).
  Zero call-path errors. Profiles RUNNING, Zoiper registered.

## PostgreSQL (24 h)

- Zero errors/fatals. 444 results / 2107+ events intact across restarts.

## Answers to «что на че и как»

- Что падает: только старые 500 health (уже чинено) и плановые 429
  перегрузки.
- Что шумит: signalwire-сертификаты (не наше), qwen-занятость (лечится
  порядком рестарта, уже записан).
- Что тихо: БД, распознавание по качеству, мост после последнего
  рестарта.
- Что делать: перепрогнать capacity probe перед подъёмом лимитов;
  остальное — наблюдать, не чинить.
