# FreeSWITCH production telephony (ADR-013) — P0-A Docker image
#
# Base: safarov/freeswitch (amd64). mod_audio_stream community READ from release deb.
# See MOD_AUDIO_STREAM.md for license boundary.

FROM debian:bookworm-slim AS modextract
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates \
    && wget -q -O /mod.deb \
        https://github.com/amigniter/mod_audio_stream/releases/download/v1.0.3/mod-audio-stream_1.0.3_amd64.deb \
    && apt-get install -y --no-install-recommends dpkg \
    && dpkg-deb -x /mod.deb /extract \
    && rm -rf /var/lib/apt/lists/*

FROM safarov/freeswitch:latest

COPY --from=modextract /extract/usr/lib/freeswitch/mod/mod_audio_stream.so \
    /usr/lib/freeswitch/mod/mod_audio_stream.so

RUN mkdir -p /etc/freeswitch \
    && cp -a /usr/share/freeswitch/conf/vanilla/. /etc/freeswitch/ \
    && sed -i '/<load module="mod_sndfile"\/>/a\    <load module="mod_audio_stream"/>' \
        /etc/freeswitch/autoload_configs/modules.conf.xml \
    && sed -i 's|value="\$${internal_auth_calls}"|value="false"|' \
        /etc/freeswitch/sip_profiles/internal.xml \
    && sed -i 's|<param name="ext-rtp-ip" value="auto-nat"/>|<param name="ext-rtp-ip" value="auto"/>|g' \
        /etc/freeswitch/sip_profiles/internal.xml \
    && sed -i 's|<param name="ext-sip-ip" value="auto-nat"/>|<param name="ext-sip-ip" value="auto"/>|g' \
        /etc/freeswitch/sip_profiles/internal.xml \
    && sed -i 's|<param name="manage-presence" value="true"/>|<param name="manage-presence" value="false"/>|' \
        /etc/freeswitch/sip_profiles/internal.xml \
    && sed -i 's|<param name="apply-inbound-acl" value="domains"/>|<param name="apply-inbound-acl" value=""/>|' \
        /etc/freeswitch/sip_profiles/internal.xml \
    && sed -i 's|<!-- <param name="rtp-start-port" value="16384"/> -->|<param name="rtp-start-port" value="16384"/>|' \
        /etc/freeswitch/autoload_configs/switch.conf.xml \
    && sed -i 's|<!-- <param name="rtp-end-port" value="32768"/> -->|<param name="rtp-end-port" value="16484"/>|' \
        /etc/freeswitch/autoload_configs/switch.conf.xml

COPY conf/dialplan/public.xml /etc/freeswitch/dialplan/public.xml
COPY conf/vars_imvera.xml /etc/freeswitch/vars_imvera.xml
COPY conf/directory/default/fs-gate-caller.xml /etc/freeswitch/directory/default/fs-gate-caller.xml
COPY conf/directory/default/zoiper.xml /etc/freeswitch/directory/default/zoiper.xml
COPY conf/autoload_configs/acl.conf.xml /etc/freeswitch/autoload_configs/acl.conf.xml
COPY conf/autoload_configs/event_socket.conf.xml /etc/freeswitch/autoload_configs/event_socket.conf.xml

RUN grep -q 'vars_imvera.xml' /etc/freeswitch/vars.xml \
    || echo '<X-PRE-PROCESS cmd="include" data="vars_imvera.xml"/>' >> /etc/freeswitch/vars.xml

EXPOSE 5060/udp 5060/tcp 8021/tcp 16384-16484/udp

# Fail fast if custom image lost mod_audio_stream (vanilla safarov has none).
HEALTHCHECK --interval=5s --timeout=5s --retries=24 --start-period=20s \
  CMD fs_cli -x 'status' | grep -qi up \
  && fs_cli -x 'module_exists mod_audio_stream' | grep -qx true

ENV SOUND_TYPES=
ENV SOUND_RATES=
