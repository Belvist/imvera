"""LiveKit telephony adapter — wraps LiveKitCallSession for TelephonyAdapter contract."""

from __future__ import annotations

import logging
from typing import Any

from packages.telephony.adapter import InboundMediaFrame, TelephonyMediaCounters
from packages.telephony.livekit_session import LiveKitCallSession, LiveKitSessionKeys

log = logging.getLogger(__name__)


class LiveKitTelephonyAdapter:
    """Media transport only — CallActor owns dialogue/VAD/STT/TTS."""

    def __init__(self, session: LiveKitCallSession) -> None:
        self._session = session
        self._open = False

    @property
    def session(self) -> LiveKitCallSession:
        return self._session

    async def open_call(
        self,
        call_id: str,
        *,
        family_id: str,
        elder_name: str,
        carrier_call_ref: str,
    ) -> None:
        if self._open:
            return
        await self._session.start()
        self._open = True

    async def push_inbound(self, frame: InboundMediaFrame) -> None:
        await self._session.push_pcm(frame.pcm_s16le, frame.sample_rate)

    async def send_outbound_pcm(self, pcm_s16le: bytes, sample_rate: int) -> None:
        await self._session.send_outbound_pcm(pcm_s16le, sample_rate)

    async def flush_outbound(self) -> None:
        await self._session.flush_outbound()

    async def wait_outbound_playout(self) -> None:
        await self._session.wait_outbound_playout()

    async def hangup(self) -> None:
        await self._session.shutdown()

    def counters(self) -> TelephonyMediaCounters:
        lk = self._session.counters
        return TelephonyMediaCounters(
            carrier_rx_frames=lk.transport_rx_frames,
            carrier_rx_bytes=lk.transport_rx_bytes,
            carrier_tx_frames=lk.livekit_audio_frames_tx,
            carrier_tx_bytes=lk.livekit_audio_bytes_tx,
            gateway_rx_frames=lk.transport_rx_frames,
            actor_rx_frames=lk.transport_rx_frames,
        )


def build_livekit_session(
    *,
    room_name: str,
    room_sid: str,
    sip_identity: str,
    sip_sid: str,
    livekit_url: str,
    api_key: str,
    api_secret: str,
    push_pcm,
    emit_stage,
    note_transport=None,
    artifact_dir=None,
    call_id: str | None = None,
    media_gate_mode: bool = False,
    publish_outbound: bool = True,
) -> LiveKitCallSession:
    from packages.telephony.livekit_session import new_livekit_call_id

    cid = call_id or new_livekit_call_id(room_name)
    return LiveKitCallSession(
        call_id=cid,
        keys=LiveKitSessionKeys(
            room_name=room_name,
            room_sid=room_sid,
            sip_participant_identity=sip_identity,
            sip_participant_sid=sip_sid,
        ),
        livekit_url=livekit_url,
        api_key=api_key,
        api_secret=api_secret,
        push_pcm=push_pcm,
        emit_stage=emit_stage,
        note_transport=note_transport,
        artifact_dir=artifact_dir,
        media_gate_mode=media_gate_mode,
        publish_outbound=publish_outbound,
    )
