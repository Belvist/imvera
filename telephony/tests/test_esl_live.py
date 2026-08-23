"""ESL streaming bridge: build a standard WAV, append PCM in a few writes
(mimicking uuid_record writing a live-growing file) and verify LiveWavReader
tail-reads exactly the NEW int16 mono samples, skipping the 44-byte header
once and never duplicating bytes across reads."""
import os
import struct
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from esl_stream import LiveWavReader  # noqa: E402


def _header(pcm_len):
    """44-byte standard WAV header for 16 kHz mono 16-bit PCM."""
    h = bytearray(44)
    h[0:4] = b"RIFF"
    h[4:8] = struct.pack("<I", 36 + pcm_len)
    h[8:12] = b"WAVE"
    h[12:16] = b"fmt "
    h[16:20] = struct.pack("<I", 16)
    h[20:22] = struct.pack("<H", 1)
    h[22:24] = struct.pack("<H", 1)
    h[24:28] = struct.pack("<I", 16000)
    h[28:32] = struct.pack("<I", 32000)
    h[32:34] = struct.pack("<H", 2)
    h[34:36] = struct.pack("<H", 16)
    h[36:40] = b"data"
    h[40:44] = struct.pack("<I", pcm_len)
    return bytes(h)


def _pcm(samples):
    return struct.pack("<%dh" % len(samples), *samples)


class LiveWavReaderTests(unittest.TestCase):
    def setUp(self):
        self.fd, self.path = tempfile.mkstemp(suffix=".wav")
        os.close(self.fd)

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def write_wav(self, chunks):
        with open(self.path, "wb") as f:
            total = sum(len(c) * 2 for c in chunks)
            f.write(_header(total))
            for c in chunks:
                f.write(_pcm(c))

    def test_returns_new_samples_after_header(self):
        chunk1 = [100] * 1600  # 0.1 s of 16k
        self.write_wav([chunk1])

        rd = LiveWavReader(self.path, sample_rate=16000)

        # first read: header skipped, returns exactly chunk1
        got1 = rd.read_new()
        self.assertEqual(len(got1), len(chunk1))
        self.assertEqual(got1[:3], [100, 100, 100])

        # second read: no new bytes -> empty
        self.assertEqual(rd.read_new(), [])

        # append more; only the new samples are returned, none duplicated
        chunk2 = [200] * 800
        with open(self.path, "ab") as f:
            f.write(_pcm(chunk2))
        got2 = rd.read_new()
        self.assertEqual(len(got2), len(chunk2))
        self.assertEqual(set(got2), {200})

    def test_handles_partial_writes_after_creation(self):
        # file created with header only (no samples yet)
        with open(self.path, "wb") as f:
            f.write(_header(0))
        rd = LiveWavReader(self.path, sample_rate=16000)
        # nothing beyond header yet
        self.assertEqual(rd.read_new(), [])
        # now samples arrive in two small bursts
        burst1 = [50] * 320
        burst2 = [-60] * 320
        with open(self.path, "ab") as f:
            f.write(_pcm(burst1))
        self.assertEqual(rd.read_new(), burst1)
        with open(self.path, "ab") as f:
            f.write(_pcm(burst2))
        self.assertEqual(rd.read_new(), burst2)

    def test_stereo_returns_left_channel_only(self):
        # record_stereo WAV: LEFT = caller, RIGHT = Vera's playback.
        left = [111, -222, 333, -444]
        right = [9999, -9999, 9999, -9999]
        interleaved = [v for pair in zip(left, right) for v in pair]
        hdr = bytearray(_header(len(interleaved) * 2))
        hdr[22:24] = struct.pack("<H", 2)  # stereo
        with open(self.path, "wb") as f:
            f.write(bytes(hdr))
            f.write(_pcm(interleaved))

        rd = LiveWavReader(self.path, sample_rate=8000)
        got = rd.read_new()
        self.assertEqual(got, left)  # RIGHT dropped entirely

        # append a partial frame (3 bytes): must not crash or duplicate
        with open(self.path, "ab") as f:
            f.write(b"\x01\x02\x03")
        self.assertEqual(rd.read_new(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)