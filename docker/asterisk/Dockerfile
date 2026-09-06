# Asterisk 22 lab image — ADR-001 (chan_websocket + ARI)
# Tag andrius/asterisk:22 verified on Docker Hub (22.8.0 tag does not exist)
FROM andrius/asterisk:22

RUN mkdir -p /etc/asterisk/generated

COPY docker/asterisk/modules.conf /etc/asterisk/modules.conf
COPY docker/asterisk/extensions.conf /etc/asterisk/extensions.conf
COPY docker/asterisk/rtp.conf /etc/asterisk/rtp.conf

EXPOSE 5060/udp 5060/tcp 8088 10000-10100/udp
