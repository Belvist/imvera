# Asterisk 22.x with chan_websocket — ADR-001 lab image
# Pin: andrius/asterisk:22 (verify modules in container after build)
FROM andrius/asterisk:22

RUN mkdir -p /etc/asterisk/generated

# Base templates; runtime secrets mounted from config/local/asterisk
COPY docker/asterisk/modules.conf /etc/asterisk/modules.conf
COPY docker/asterisk/extensions.conf /etc/asterisk/extensions.conf
COPY docker/asterisk/rtp.conf /etc/asterisk/rtp.conf

EXPOSE 5060/udp 8088 10000-10100/udp
