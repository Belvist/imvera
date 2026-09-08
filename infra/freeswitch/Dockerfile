# FreeSWITCH production telephony (ADR-013)
#
# P0 uses mod_audio_stream for transport validation only.
# See docs/adr/013-production-telephony-freeswitch.md for license boundary:
#   community = uplink; bidirectional playback = commercial OR mod_imvera_audio.
#
# Upstream: https://github.com/amigniter/mod_audio_stream
# Pin commit/tag in infra/freeswitch/MOD_AUDIO_STREAM.md before production.

FROM safarov/freeswitch:1.10.11

COPY conf/ /etc/freeswitch/

EXPOSE 5060/udp 5060/tcp 8021/tcp 16384-32768/udp

CMD ["freeswitch", "-nonat", "-nf"]
