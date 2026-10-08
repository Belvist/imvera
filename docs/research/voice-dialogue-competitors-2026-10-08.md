# Конкуренты: что переносим в IMVERA

Проверка официальных страниц: 2026-10-08 UTC, все6 ответили HTTP200.
[URLs, final URLs и SHA256 полученных документов](competitors-2026-10-08-sources.json).
Прочитаны публичные материалы. Не запускались платные API, vendor calls,
демо-агенты или сравнительное прослушивание. Это сравнение заявленной
архитектуры/продукта; русская телефонная речь и качество конкурентов NOT_RUN.

| Продукт и источник | Что описывает поставщик | Практическое решение для IMVERA |
| --- | --- | --- |
| [Newo](https://newo.ai/platform/newo-zero-hallucination-architecture) | Model handles language; Observer tracks evidence and next steps, Supervisor executes gated actions. Страница прямо признаёт возможность ошибок и пределы STT | Сохранить code-owned evidence/action authority; недостаточно произнести «передам» — нужны Core ack/recipient receipts. Не копировать параллельные brains в наш reducer |
| [Fish Agents](https://docs.fish.audio/agents/overview.md) | Hosted realtime agents, prompt/knowledge/tools, phone/web/API, управляемые speech recognition/turn-taking/TTS; public beta | Fish уже не только TTS. Ориентиры — версии agent/config, целостный realtime SDK и настоящая audio acceptance; не считать beta независимым доказательством промышленной надёжности |
| [Retell](https://docs.retellai.com/build/conversation-flow/overview) | Conversation-flow nodes с instructions/actions и transitions. Документация отмечает проблемы границ узлов, когда человек даёт информацию заранее или меняет решение | Один ответ закрывает несколько нужд; уже сказанное не спрашивать для прохождения ступени. Разговорный ход может занимать несколько turns; не делать node/question FSM рядом с EngineState |
| [Vapi](https://docs.vapi.ai/customization/speech-configuration) | Start/Stop Speaking Plan, smart endpointing по audio/text и контроль реакций на короткие acknowledgments | Начало/окончание пользовательского turn и слышимая остановка Веры — отдельные измеримые задачи. Сам streaming TTS не решает медленные паузы и перебивания |
| [PolyAI](https://poly.ai/technology) | Proprietary LLM + agentic runtime, ASR, generative/retrieval dialogue policy, передача контекста человеку, SIP/PSTN | Обсуждать содержание и держать тему; integration/result столь же важны, как голос. Их sub-second/миллиардные заявления здесь не проверены и не переносятся на наши M5/CPU |
| [ElliQ](https://elliq.com/) | Companion для пожилых: общение, досуг, health/wellness и связь с близкими; домашнее устройство | Более близок по пользователю и смыслу заботы, отличается аппаратным каналом. Оценивать burden, patient pacing и личную непрерывность, а не только процент закрытых полей |

Newo не обещает математическое отсутствие hallucinations: это название
control design. Retell также не скрывает цену жёстких flow boundaries.
Вывод для нас: нужен гибкий выбор следующего полезного действия, строгие
факты/согласие и качественный realtime вокруг него. Больше готовых фраз
не заменяют ни одного из этих владельцев.

## Что действительно сравнивать

Один и тот же набор consented/synthetic elder phone WAV и контекстов:
несколько жалоб; 3–4 факта сразу; история о дочери; медленная речь;
исправление; отказ от вопроса; пользовательский вопрос; смена/возврат темы;
symptom inside story; urgency/negation/third party; interruption; stop call.
Фиксировать provider/version/language/телефонную полосу и исходные записи.

Считать известные повторные вопросы, clarification burden, потерю темы,
unsupported facts/actions, completion и end-of-speech→audible-first-PCM.
Слушатели оценивают тепло и удобство вслепую; отдельно проверяем safety и
actual action receipts. Неуспешные/timeout calls включаются в отчёт.
До появления этих данных у всех конкурентов результаты **NOT_RUN**.

Не меняем провайдеры, лицензии или live generative запрет на основании этой
таблицы. Возможный constrained model benchmark из ADR-028 — отдельный
низкорисковый эксперимент с memory/latency/grounding measurements.
