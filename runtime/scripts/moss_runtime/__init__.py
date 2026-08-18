"""Vendored MOSS-TTS-Nano ONNX CPU runtime (OpenMOSS/MOSI.AI, apache-2.0).

Files from https://github.com/OpenMOSS/MOSS-TTS-Nano with minimal patches:
- torch/torchaudio removed; reference audio is loaded with soundfile/librosa;
- relative imports (files live in this package, not at the repo root).
"""
