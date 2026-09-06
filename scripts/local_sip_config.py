"""Shared local SIP credentials — Zoiper JSON + rendered Asterisk configs."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZOIPER_JSON = ROOT / "config" / "local" / "zoiper.json"
ASTERISK_DIR = ROOT / "config" / "local" / "asterisk"
ARI_USER = "imvera"
STASIS_APP = "imvera"


def load_or_create() -> dict:
    ASTERISK_DIR.mkdir(parents=True, exist_ok=True)
    if ZOIPER_JSON.exists():
        data = json.loads(ZOIPER_JSON.read_text())
    else:
        data = {
            "sip_server": "127.0.0.1",
            "transport": "UDP",
            "port": 5060,
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

    (ASTERISK_DIR / "pjsip.conf").write_text(
        f"""[global]
type=global
endpoint_identifier_order=ip,username,anonymous

[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060

[1001]
type=endpoint
context=imvera-local
disallow=all
allow=ulaw,alaw,slin16
auth=1001
aors=1001
direct_media=no

[1001]
type=auth
auth_type=userpass
password={sip_pass}
username=1001

[1001]
type=aor
max_contacts=5
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
[imvera-capture]
type = websocket_client
uri = ws://{gateway_host}/asterisk/capture
protocols = media
transport_data = f(json)
encryption = no
tls_enabled = no
verify_server_cert = no

[imvera-inject]
type = websocket_client
uri = ws://{gateway_host}/asterisk/inject
protocols = media
transport_data = f(json)
encryption = no
tls_enabled = no
verify_server_cert = no
"""
    )

    cfg["ari_user"] = ARI_USER
    cfg["ari_password"] = ari_pass
    cfg["stasis_app"] = STASIS_APP
    ZOIPER_JSON.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
