"""Controlled providers verify benchmark plumbing; not a capacity measurement."""
import wave
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AsrQuality
from packages.contracts.providers import AudioChunk
from packages.contracts.stt import STTResult
from scripts import capacity_probe as probe


def write_wav(path, rate=8000, channels=1):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b'\0\0' * 80 * channels)


def test_wave_rate_and_frames_are_read_from_riff_metadata(tmp_path):
    path = tmp_path / 'audio.wav'
    write_wav(path)
    assert probe.load_pcm(path) == (b'\0\0' * 80, 8000)
    write_wav(path, channels=2)
    with pytest.raises(ValueError, match='mono'):
        probe.load_pcm(path)


@pytest.mark.parametrize('fail_pcm', [False, True, 'truncated_reply'])
def test_actual_stt_output_and_canonical_speech_drive_benchmark(monkeypatch, tmp_path, fail_pcm):
    path = tmp_path / 'speech.wav'
    write_wav(path)
    captured = SimpleNamespace(stt=[], engine=[], tts=[], delivered=[])

    class STT:
        def __init__(self, url):
            pass

        async def transcribe_final(self, pcm, rate, **identity):
            captured.stt.append((rate, identity))
            return STTResult(text='Рука болит.', raw_text='рука болит',
                             asr_quality=AsrQuality.LOW)

    class TTS:
        def __init__(self, url):
            pass

        async def synthesize(self, text, **identity):
            captured.tts.append((text, identity))
            if fail_pcm is not True:
                yield AudioChunk(b'\0\0' * 160, 16000, 0)
                if fail_pcm == 'truncated_reply' and identity['generation_id'] == 'reply':
                    from packages.contracts.providers import ProviderUnavailable
                    raise ProviderUnavailable('controlled truncated stream')
                yield AudioChunk(b'\0\0' * 160, 16000, 1, True)

    class Session:
        def __init__(self, **kwargs):
            self._engine = SimpleNamespace(state=SimpleNamespace(call_closed=False))

        def uses_dialogue_engine(self):
            return True

        def result(self, text, generation):
            return SimpleNamespace(validated=SimpleNamespace(
                speech=text, generation_id=generation, intent='probe', allowed=True),
                followup_speak_effects=[], from_engine=True)

        def start(self):
            return self.result('Начальная каноническая речь.', 'opening')

        def handle_user_text(self, text, **kwargs):
            captured.engine.append((text, kwargs))
            return self.result('Канонический ответ о руке.', 'reply')

        def mark_spoken_action(self, generation):
            captured.delivered.append(generation)
            return True

        def pop_engine_playout_followup(self):
            return None

    monkeypatch.setattr(probe, 'HttpSTTProvider', STT)
    monkeypatch.setattr(probe, 'HttpTTSProvider', TTS)
    monkeypatch.setattr(probe, 'CallSession', Session)
    result = probe._one_call(0, [path], {'stt': 'isolated', 'tts': 'isolated'})
    if fail_pcm is True:
        assert result['errors'] == [{'stage': 'opening', 'type': 'RuntimeError'}]
        assert result['completed_turns'] == 0
        assert captured.delivered == [] and captured.engine == []
    elif fail_pcm == 'truncated_reply':
        assert result['errors'] == [{'stage': 'tts', 'type': 'ProviderUnavailable'}]
        assert result['completed_turns'] == 0
        assert captured.delivered == ['opening']
        row = result['turns'][0]
        assert row['tts'][0]['first_pcm_ms'] is not None
        assert row['tts'][0]['complete_ms'] is None
        assert row['input_to_first_pcm_ms'] is not None
    else:
        assert captured.engine[0][0] == 'Рука болит.'
        assert captured.engine[0][1]['asr_quality'] == AsrQuality.LOW
        assert captured.stt[0][0] == 8000
        assert captured.stt[0][1]['call_id'] == captured.tts[1][1]['call_id']
        assert [entry[0] for entry in captured.tts] == [
            'Начальная каноническая речь.', 'Канонический ответ о руке.']
        assert captured.delivered == ['opening', 'reply']
        assert result['completed_turns'] == 1 and result['tts_calls'] == 2
        row = result['turns'][0]
        assert row['tts'][0]['first_pcm_ms'] <= row['tts'][0]['complete_ms']
        assert row['tts'][0]['audio_seconds'] == .02


def test_missing_measurement_is_not_zero_latency_and_failures_remain_visible():
    summary = probe.summarize([{'turns': [{'stt_ms': 5, 'complete': False}],
                               'completed_turns': 0, 'stt_calls': 1, 'tts_calls': 0,
                               'errors': [{'stage': 'tts', 'type': 'ProviderUnavailable'}]}])
    assert summary['attempted_turns'] == 1 and summary['completed_turns'] == 0
    assert summary['latency']['input_to_first_pcm_ms']['p95_ms'] is None
    assert summary['errors_by_stage_type'] == {'tts/ProviderUnavailable': 1}
