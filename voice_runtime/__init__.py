"""MossVoice VoiceRuntime (read.md G3).

Continuous-media telephony runtime: listens on FreeSWITCH Event Socket,
attaches a live stereo tape to every answered runtime call, runs an
always-on VAD on the LEFT (caller) channel, and cancels TTS/playback on
barge-in. The legacy `moss_agent.lua` is GONE; runtime calls reach
FreeSWITCH via the dialplan extension 4400 (production) / 4402 (loopback
self-test) that only answers + parks/sleeps.
"""
__version__ = "0.2.0"