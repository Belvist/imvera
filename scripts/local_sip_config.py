"""Shared local SIP credentials — Zoiper JSON + rendered Asterisk configs."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZOIPER_JSON = ROOT / "config" / "local" / "zoiper.json"
ASTERISK_DIR = ROOT / "config" / "local" / "asterisk"
ARI_USER = "imvera"
STASIS_APP = "imvera"


def detect_media_host() -> str:
    """Host IPv4 for RTP SDP — must be bindable on the host and reachable from Docker."""
    env = os.environ.get("IMVERA_SIP_MEDIA_HOST")
    if env:
        return env
    try:
        ip = subprocess.check_output(
            ["ipconfig", "getifaddr", "en0"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if ip:
            return ip
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        probe.close()
    if ip.startswith(("127.", "240.")):
        return "127.0.0.1"
    return ip


def load_or_create() -> dict:
    ASTERISK_DIR.mkdir(parents=True, exist_ok=True)
    if ZOIPER_JSON.exists():
        data = json.loads(ZOIPER_JSON.read_text())
        if data.get("port") == 5060:
            data["port"] = 5062
    else:
        data = {
            "sip_server": "127.0.0.1",
            "transport": "UDP",
            "port": 5062,
            "username": "1001",
            "password": secrets.token_urlsafe(12),
            "vera_extension": "7000",
            "ari_user": ARI_USER,
            "ari_password": secrets.token_urlsafe(16),
            "stasis_app": STASIS_APP,
        }
        ZOIPER_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    render_asterisk_configs(data)
    return data


def render_asterisk_configs(cfg: dict) -> None:
    sip_pass = cfg["password"]
    ari_pass = cfg.get("ari_password", secrets.token_urlsafe(16))
    gateway_host = cfg.get("gateway_host", "host.docker.internal:9200")
    media_host = detect_media_host()
    cfg["media_host"] = media_host

    (ASTERISK_DIR / "pjsip.conf").write_text(
        f"""[global]
type=global
endpoint_identifier_order=ip,username,anonymous

[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
local_net=172.16.0.0/12
local_net=192.168.0.0/16
local_net=10.0.0.0/8
external_media_address={media_host}
external_signaling_address=127.0.0.1

[transport-tcp]
type=transport
protocol=tcp
bind=0.0.0.0:5060
local_net=172.16.0.0/12
local_net=192.168.0.0/16
local_net=10.0.0.0/8
external_media_address={media_host}
external_signaling_address=127.0.0.1

[1001]
type=endpoint
context=imvera-local
disallow=all
allow=ulaw,alaw
auth=1001
aors=1001
from_domain=127.0.0.1
direct_media=no
rtp_symmetric=yes
force_rport=yes
media_use_received_transport=yes
rtp_keepalive=10

[1001]
type=auth
auth_type=userpass
password={sip_pass}
username=1001
realm=127.0.0.1

[1001]
type=aor
max_contacts=10
remove_existing=yes
"""
    )

    (ASTERISK_DIR / "ari.conf").write_text(
        f"""[general]
enabled=yes
pretty=yes
allowed_origins=*

[{ARI_USER}]
type=user
read_only=no
password={ari_pass}
"""
    )

    (ASTERISK_DIR / "http.conf").write_text(
        """[general]
enabled=yes
bindaddr=0.0.0.0
"""
    )

    (ASTERISK_DIR / "rtp.conf").write_text(
        """[general]
rtpstart=10000
rtpend=10100
strictrtp=no
"""
    )

    (ASTERISK_DIR / "chan_websocket.conf").write_text(
        """[general]
control_message_format = json
"""
    )

    (ASTERISK_DIR / "extensions.conf").write_text(
        f"""[imvera-local]
exten => {cfg.get('vera_extension', '7000')},1,NoOp(IMVERA voice entry)
 same => n,Stasis({STASIS_APP})
 same => n,Hangup()
"""
    )

    (ASTERISK_DIR / "websocket_client.conf").write_text(
        f"""; IMVERA voice gateway — generated, do not commit secrets
[imvera_capture]
type = websocket_client
uri = ws://{gateway_host}/asterisk/capture
protocols = media
connection_type = per_call_config
connection_timeout = 5000
reconnect_interval = 500
reconnect_attempts = 3
tls_enabled = no
verify_server_cert = no

[imvera_inject]
type = websocket_client
uri = ws://{gateway_host}/asterisk/inject
protocols = media
connection_type = per_call_config
connection_timeout = 5000
reconnect_interval = 500
reconnect_attempts = 3
tls_enabled = no
verify_server_cert = no
"""
    )

    cfg["ari_user"] = ARI_USER
    cfg["ari_password"] = ari_pass
    cfg["stasis_app"] = STASIS_APP
    cfg["sip_server"] = "127.0.0.1"
    cfg["media_host"] = media_host
    zoiper_host = media_host
    cfg["zoiper_setup"] = {
        "host": zoiper_host,
        "port": cfg.get("port", 5062),
        "transport": "UDP",
        "transport_tcp_also_ok": True,
        "username": cfg.get("username", "1001"),
        "domain": zoiper_host,
        "disable_dns_srv": True,
        "avoid_port": 5060,
        "avoid_port_reason": "FreeSWITCH on this Mac — 403/480",
        "avoid_host": "127.0.0.1",
        "avoid_host_reason": "Docker Asterisk cannot RTP to localhost — use LAN IP",
        "rtp_note": f"Signaling + RTP via {zoiper_host}:{cfg.get('port', 5062)}",
    }
    ZOIPER_JSON.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
