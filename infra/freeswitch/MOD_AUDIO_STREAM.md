# mod_audio_stream dependency (P0 validation only — NOT permanent production lock-in)
#
# Repository: https://github.com/amigniter/mod_audio_stream
# FreeSWITCH: 1.10.x (image safarov/freeswitch:1.10.11)
#
# Edition boundary (upstream README, 2026-09):
#   - Community: primarily uplink streaming to WebSocket
#   - Commercial bidirectional playback: v1.0.3+, free tier ≤10 concurrent channels
#
# Production must explicitly choose BEFORE pilot:
#   A) Licensed bidirectional mod_audio_stream
#   B) Custom mod_imvera_audio on FreeSWITCH media-bug API
#
# P0 gate may use mod_audio_stream to prove FS answer + PCM path.
# Do NOT treat free bidirectional tier as silent eternal dependency.
