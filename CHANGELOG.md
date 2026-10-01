# Changelog

## Unreleased — 2026-09-30

- Route bounded NLP act votes into canonical dialogue turns with truthful usage trace.
- Retire generative bridge rewriting; deliver canonical SDK speech directly to TTS.
- Keep accepted slots, mission progress and current evidence coherent.
- Preserve polite refusal after goodbye without inferring future-consent revocation.
- Discharge not-recalled episode/custom questions with explicit unanswered evidence.
- Suspend custom missions for health clarification, then resume the original goal.
- Require extractive free-text values; separate health interruptions from general task answers.
- Retain the care signal for explicitly active symptoms after questioning finishes.
- Correct summary noun-list grammar and custom greeting name addressing.
- Add SDK integration/agent guidance, competitor research and reproducible text demos.
- Keep GigaAM cache tests offline while verifying missing-tokenizer downloads explicitly.

Live voice acceptance and model-artifact verification remain pending; this is a
development-branch change, not a deployed release.
