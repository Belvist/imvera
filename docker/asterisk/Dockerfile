FROM andrius/asterisk:20

COPY docker/asterisk/pjsip.conf /etc/asterisk/pjsip.conf
COPY docker/asterisk/extensions.conf /etc/asterisk/extensions.conf
COPY docker/asterisk/ari.conf /etc/asterisk/ari.conf
COPY docker/asterisk/http.conf /etc/asterisk/http.conf
COPY docker/asterisk/rtp.conf /etc/asterisk/rtp.conf

EXPOSE 5060/udp 8088 10000-10100/udp
