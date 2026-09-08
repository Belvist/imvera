#!/usr/bin/env python3
"""Configure LiveKit SIP inbound trunk + per-call dispatch rule (local dev).

Privacy note: dispatchRuleIndividual may embed caller digits in LiveKit room_name.
IMVERA maps room_sid → opaque call_id; never use room_name as application identifier.
"""

from __future__ import annotations

import asyncio
import os
import sys


async def _setup() -> int:
    from livekit.api import (
        CreateSIPDispatchRuleRequest,
        CreateSIPInboundTrunkRequest,
        ListSIPDispatchRuleRequest,
        ListSIPInboundTrunkRequest,
        LiveKitAPI,
        SIPDispatchRule,
        SIPDispatchRuleIndividual,
        SIPInboundTrunkInfo,
    )

    http_url = os.environ.get("LIVEKIT_HTTP_URL", "http://127.0.0.1:7880")
    api_key = os.environ.get("LIVEKIT_API_KEY", "devkey")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "secret")
    number = os.environ.get("LIVEKIT_SIP_INBOUND_NUMBER", "+15550001000")
    room_prefix = os.environ.get("LIVEKIT_ROOM_PREFIX", "imvera-call-")

    api = LiveKitAPI(http_url, api_key, api_secret)
    sip = api.sip
    try:
        trunks = await sip.list_inbound_trunk(ListSIPInboundTrunkRequest())
        trunk_id = None
        for t in trunks.items:
            if number in (t.numbers or []):
                trunk_id = t.sip_trunk_id
                print(f"inbound trunk exists: {trunk_id}")
                break
        if trunk_id is None:
            trunk = SIPInboundTrunkInfo(name="imvera-local-inbound", numbers=[number])
            created = await sip.create_inbound_trunk(CreateSIPInboundTrunkRequest(trunk=trunk))
            trunk_id = created.sip_trunk_id
            print(f"created inbound trunk: {trunk_id} number={number}")

        rules = await sip.list_dispatch_rule(ListSIPDispatchRuleRequest())
        for r in rules.items:
            if r.name == "imvera-individual-dispatch":
                print(f"dispatch rule exists: {r.sip_dispatch_rule_id}")
                return 0

        rule = SIPDispatchRule(
            dispatch_rule_individual=SIPDispatchRuleIndividual(room_prefix=room_prefix)
        )
        created_rule = await sip.create_dispatch_rule(
            CreateSIPDispatchRuleRequest(
                rule=rule,
                name="imvera-individual-dispatch",
                trunk_ids=[trunk_id] if trunk_id else [],
            )
        )
        print(f"created dispatch rule: {created_rule.sip_dispatch_rule_id} prefix={room_prefix}")
        return 0
    finally:
        await api.aclose()


def main() -> int:
    try:
        return asyncio.run(_setup())
    except Exception as exc:
        print(f"livekit-setup-sip: FAILED {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
