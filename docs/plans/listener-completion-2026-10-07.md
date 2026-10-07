# Listener completion: shared whole-utterance meaning

Baseline feature/voice-zoiper-m5 **4d3ad19934e2212ab71982c466c9b3b6a92ffe82**.
Its exact CI37643179274 passed11/11,3495 full tests. Cloud/M5 access unchanged.

After a heard personal invitation/listening acknowledgment, «Нет, ничего»,
«Вроде бы нет» and «Больше ничего» currently become another personal statement
and produce a listener ACK. The existing discourse floor helper recognizes
only its short literal set and grammatical «всё» forms. This is topic completion,
not an instruction to terminate the whole call or evidence of health.

Reuse the existing pure whole-utterance completion classifier from the closing
owner in the discourse listener's finished predicate. Do not change that
classifier, controls or consent. The existing selector decides whether to
resume required health work or summarize. No new phrase list, model, scheduler,
state field or timer. The lazy read introduces no import-time reducer cycle.

Before source edits reproduce three whole completion shapes and a mixed
statement «Вроде нет, а потом ... поездку к морю» as a negative control.
Assert record/ring preservation, topic completion rather than hangup, and
continued story on mixed words. Run full original gates and exact CI again.
Phone timing/warmth/SIP acceptance still needs the target and real recording.
