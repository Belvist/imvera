"""PJSUA2 blackbox configuration — PCMU/PCMA first, codec fields in result.json."""

from __future__ import annotations

import os
from dataclasses import dataclass

from tools.blackbox_caller.config import BlackboxConfig
from tools.blackbox_caller.config import load_config as load_blackbox_config


@dataclass(frozen=True)
class Pjsua2Config:
    blackbox: BlackboxConfig
    offered_codecs: tuple[str, ...]
    prefer_codec: str
    registrar_uri: str
    id_uri: str


def load_pjsua2_config() -> Pjsua2Config:
    base = load_blackbox_config()
    host = base.sip_domain or base.sip_host
    port = base.sip_port
    prefer = os.environ.get("IMVERA_PJSUA2_CODEC", "PCMU").strip().upper()
    offered = tuple(
        c.strip().upper()
        for c in os.environ.get("IMVERA_PJSUA2_OFFERED_CODECS", "PCMU,PCMA").split(",")
        if c.strip()
    )
    return Pjsua2Config(
        blackbox=base,
        offered_codecs=offered,
        prefer_codec=prefer,
        registrar_uri=f"sip:{host}:{port}",
        id_uri=f"sip:{base.sip_user}@{host}",
    )
