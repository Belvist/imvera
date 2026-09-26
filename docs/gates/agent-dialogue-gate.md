# Agent dialogue gate (no Zoiper)

Agents (Grok Bot / OpenCode) must prove dialogue behaviour **without** waiting
for a human handset.

| Layer | Command | What it proves |
|---|---|---|
| **A** | `make agent-dialogue-gate` | CallSession → DialogueEngine on owner wellness/decline checklist |
| **B** | `make live-call-1` / `make live-debug-1` | Real SIP/RTP via FreeSWITCH (lab up) |

Layer A report: `.run/agent_gates/latest.json`.

Strict mode (fail if «более-менее» opens concern):  
`python3 scripts/agent_dialogue_gate.py --strict-first-probe`

Do **not** claim CDK/live-class fixes closed without Layer A PASS.  
SIP/STT bugs still need Layer B when the stack is up.
