"""Dialogue quality harness (Dialogues 2.0, phase 2c — now live).

Offline, deterministic re-runs of the dialogue state machine: scripted call
scenarios are fed to a FRESH Agent (llm=None -> every turn is plan+scripted
fallback, no model, no audio, no DB). Each turn is checked against the
INTENDED content-first behaviour and the run collects global quality metrics:

    repeat_rate   доля реплик типа «Повторите»/пустых-ходов
    forced_topic  число интентов, форсирующих тему повестки поверх нарратива
    double_q      реплик с >1 вопросительным знаком
    promises      реплик с обещаниями «вызову/позвоню/...»
    guards        замен сегментов гвардами (mirror/latin/haluc)

Run:
    python3 voice-lab/dialog_quality.py            # печать сводки, exit 0
    python3 voice-lab/dialog_quality.py --strict  # exit 1 при провале сценариев

Особенность: пред-рефакторный код НЕ имеет аргумента `reason` у plan_reply —
харнесс интроспектирует сигнатуру и вызывает с reason только когда он есть.
"""

import inspect
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "telephony"))

from core.dialogue import Agent  # noqa: E402

_HAVE_REASON = "reason" in inspect.signature(Agent.plan_reply).parameters

_PROMISE_RE = re.compile(r"вызову|позвоню|отправлю|предупрежу|передам|сообщу",
                         re.I)
# «Мёртвые» повторы: чистые просьбы повторить ("Повторите, пожалуйста",
# "Скажите ещё раз") без продуктивного якоря. Якорная лестница (якорь да/нет,
# эскалация, тихие ходы) сюда НЕ входит — она и есть фикс.
_REPEAT_RE = re.compile(
    r"\bповторит|не расслышал|не разобрал|акустика подводит|переспросит|"
    r"скажите ещё раз|ещё раз, пожалуйста\b", re.I)
_FORCE_RE = re.compile(r"спросить про «|перейти к теме «|вопросом спросить про")


# ---------------------------------------------------------------------------
# Сценарии. turns: (user_text, reason|None, {checks})
#  check-и (все опциональные):
#   not_force_topic  intent НЕ форсирует тему повестки
#   idx_unchanged    индекс повестки после хода не сдвинулся
#   no_repeat        реплика не похожа на «Повторите»
#   contains <sub>   итоговый текст содержит подстроку
#   intent_contains <sub>
#   one_question     <= 1 вопросительный знак
#   terminal         диалог завершён
#   not_terminal     диалог продолжается
# ---------------------------------------------------------------------------

SCENARIOS = [
    ("полный ход повестки", [
        ("да, всё хорошо", None, {"one_question": True}),
        ("настроение хорошее, спасибо", None, {"one_question": True}),
        ("спала хорошо", None, {"one_question": True}),
        ("всё хорошо, буду ещё читать", None, {"one_question": True}),
        ("хорошо, запишите для них пару слов", None, {"one_question": True}),
    ]),
    ("нарратив не форсирует тему", [
        ("да, всё хорошо", None, {}),          # самочувствие закрыто -> настроение
        ("Внучка сегодня приезжала, мы с ней чай пили, так хорошо посидели.",
         None, {"not_force_topic": True, "idx_unchanged": True,
                "no_repeat": True}),
        ("да, всё хорошо", None, {"idx_unchanged": True}),  # тема та же
    ]),
    ("жалоба перебивает повестку", [
        ("да, всё хорошо", None, {}),
        ("голова болит и кружится", None,
         {"intent_contains": "уточнить", "idx_unchanged": True}),
        ("нет, сейчас отпустило", None, {"no_repeat": True}),
    ]),
    ("тишина не залипает в повторе", [
        ("", None, {}),
        ("", None, {}),
        ("", None, {"no_repeat": True}),
    ]),
    ("низкая уверенность STT — якорь, а не повтор", [
        ("", "low_conf", {"contains": "хорошо или плохо", "no_repeat": True}),
    ]),
    ("эхо-гейт — повтор без зацикливания", [
        ("да, всё хорошо", None, {}),
        # 1st echo (Vera's last reply back from the mix) -> plain repeat
        # request (acceptable); NOT an anchor — anchor comes on the 2nd echo.
        ("Здравствуйте! Это Имвэра. Как вы себя чувствуете?", "echo", {}),
        ("", "echo", {"contains": "хорошо или плохо"}),  # second — anchor
    ]),
    ("вопрос родных доходит дословно", [
        ("да, всё хорошо", None, {}),
        ("настроение хорошее, спасибо", None, {}),
        ("спала хорошо", None, {}),
        ("всё хорошо, буду ещё читать", None, {}),
        # closing «передать родным» hands the family question VERBATIM
        # (the reply after this turn IS the spoken family question)
        ("хорошо, запишите для них пару слов", None,
         {"contains": "Приняла ли ты таблетки сегодня?"}),
        # the family answer closes the last topic -> wrap-up (any of the
        # rotating wrap-up phrasings, all promise-free, all mention запис)
        ("приняла, всё хорошо", None,
         {"contains": "записа"}),
    ]),
    ("прощание-по-ошибке подтверждается", [
        ("всё хорошо", None, {}),
        ("до свидания", None, {"not_terminal": True, "one_question": True}),
        ("да", None, {"terminal": True}),
    ]),
    ("ремонт: повтор последней реплики", [
        ("Скажите ещё раз, пожалуйста", None, {"contains": "Повторяю"}),
    ]),
    ("приветствие — тепло и один раз", [
        ("Здравствуйте!", None, {"one_question": True, "no_repeat": True}),
        ("Здравствуйте ещё раз", None, {}),
    ]),
    # ---- 2026-08-29 REAL-CALL regressions (from 59064eb2d1a9 audit) ----
    ("реальный звонок: недомогание -> отпустило -> всё хорошо -> отказ -> давай пока", [
        # STT transcript conf 1.00: the caller opens with a real complaint.
        ("привет, хорошо, но сегодня самочувствие не очень", None,
         {"intent_contains": "уточнить", "idx_unchanged": True,
          "no_repeat": True}),
        # conf 0.97: "сейчас неплохо, уже хорошо встало" — Vera accepts.
        ("сейчас в данный момент неплохо, мне уже хорошо встало", None,
         {"no_repeat": True, "one_question": True}),
        # conf 0.75: "всё хорошо" closes the topic.
        ("всё хорошо", None, {"one_question": True}),
        # conf 0.91: polite decline — honoured, NO pushing follow-up, and
        # no "да, конечно, добавьте что-нибудь" (the old bug).
        ("нет спасибо", None, {"not_push": True, "no_repeat": True,
                               "not_contains": "добавите"}),
        # conf 0.93: "давай, пока" — the P-CLOSE1 fix: END the call now.
        ("давай, пока", None, {"terminal": True,
                               "not_contains": "хорошо или плохо"}),
    ]),
    ("отказ -> тишина завершает без якоря", [
        ("да, всё хорошо", None, {}),
        ("нет, спасибо, ничего не надо", None, {"not_push": True}),
        ("", "low_conf", {"terminal": True,
                          "not_contains": "хорошо или плохо"}),
    ]),
    ("пустой ход после отказа не якорит", [
        ("да, всё хорошо", None, {}),
        ("спасибо, не надо", None, {"not_push": True}),
        ("", None, {"terminal": True, "not_contains": "хорошо или плохо"}),
    ]),
    # ---- 2026-08-29 from ca81bc3ac2c7 (real call, turn 7) ----
    ("подтверждение связи на якоре — возврат к теме", [
        ("", None, {"contains": "хорошо или плохо"}),  # 1st silence -> anchor
        ("да, да, да, я тебя слышу", None,
         {"not_contains": "рада, что вы говорите",
          "one_question": True}),
    ]),
]


class _FailedScenario(Exception):
    pass


def _plan(agent, text, reason):
    args = (text,) if not _HAVE_REASON else (text,)
    kwargs = {"reason": reason} if (reason and _HAVE_REASON) else {}
    return agent.plan_reply(*args, **kwargs)


def _run_turns(agent, turns, problems, metrics):
    for text, reason, checks in turns:
        before_idx = getattr(agent, "_agenda_idx", 0)
        # Qwen3 honest: None -> low (U9). Harness must set high explicitly
        # for normal turns; low_conf scenario stays low.
        if reason == "low_conf":
            agent.observe_confidence(0.2)
        else:
            # empty/no_speech and normal high both advance only on high
            agent.observe_confidence(0.85)
        plan = _plan(agent, text, reason)
        agent.last_intent = plan.get("intent") or ""
        # с llm=None итоговый сказанный текст = фолбэк плана
        reply = plan.get("fallback") or ""
        if plan.get("intent"):
            intent = plan.get("intent") or ""
            if _FORCE_RE.search(intent) and len(text.split()) > 4:
                metrics["forced_topic"] += 1
        # ---- метрики по тексту ----
        if _REPEAT_RE.search(reply):
            metrics["repeat_rate"] += 1
        if reply.count("?") > 1:
            metrics["double_q"] += 1
        if _PROMISE_RE.search(reply):
            metrics["promises"] += 1
        # ---- проверки сценария ----
        for check, arg in checks.items():
            if check == "not_force_topic" and _FORCE_RE.search(
                    plan.get("intent") or ""):
                problems.append(f"  {text!r}: intent форсирует тему: "
                                f"{plan.get('intent')!r}")
            if check == "idx_unchanged" and \
                    getattr(agent, "_agenda_idx", 0) != before_idx:
                problems.append(f"  {text!r}: повестка сдвинулась "
                                f"{before_idx}->{agent._agenda_idx}")
            if check == "no_repeat" and _REPEAT_RE.search(reply):
                problems.append(f"  {text!r}: похоже на повтор: {reply!r}")
            if check == "contains" and arg not in reply:
                problems.append(f"  {text!r}: нет {arg!r} в {reply!r}")
            if check == "not_contains" and arg in reply:
                problems.append(f"  {text!r}: не должно быть {arg!r} в "
                                f"{reply!r}")
            if check == "not_push" and ("?" in reply or _REPEAT_RE.search(
                    reply)):
                problems.append(f"  {text!r}: отказ встречен вопросом/"
                                f"повтором: {reply!r}")
            if check == "intent_contains" and arg not in (
                    plan.get("intent") or ""):
                problems.append(f"  {text!r}: интент без {arg!r}: "
                                f"{plan.get('intent')!r}")
            if check == "one_question" and reply.count("?") > 1:
                problems.append(f"  {text!r}: {reply.count('?')} вопроса "
                                f"в {reply!r}")
            if check == "terminal" and not agent.finished:
                problems.append(f"  {text!r}: звонок не завершён")
            if check == "not_terminal" and agent.finished:
                problems.append(f"  {text!r}: звонок завершён раньше времени")
        # текст последней реплики для эхо-сценариев/ремонта
        if reply:
            agent._last_reply = reply if not plan.get("intent") else reply


def main():
    strict = "--strict" in sys.argv
    if "--help" in sys.argv:
        print(__doc__)
        return 0

    metrics = {"repeat_rate": 0, "forced_topic": 0, "double_q": 0,
               "promises": 0, "guards": 0, "turns": 0}
    results = []

    for name, turns in SCENARIOS:
        agent = Agent(llm=None)
        agent.start_check_in()
        if "вопрос родных" in name:
            agent.set_family_questions([
                {"id": "q1", "text": "Приняла ли ты таблетки сегодня?",
                 "author": "дочь"}])
        problems = []
        metrics["turns"] += len(turns)
        _run_turns(agent, turns, problems, metrics)
        ok = not problems
        results.append((name, ok, problems))
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        for p in problems:
            print(p)

    repeat = 0
    total = metrics["turns"]
    if total:
        repeat = metrics["repeat_rate"]
    print("\n--- МЕТРИКИ ---")
    print(f"ходов              {total}")
    print(f"повторов           {metrics['repeat_rate']}"
          f" ({repeat / total:.0%} ходов)")
    print(f"форсированных тем  {metrics['forced_topic']}")
    print(f"двойных вопросов   {metrics['double_q']}")
    print(f"обещаний           {metrics['promises']}")
    print(f"ходов за гвардами  {metrics['guards']}")

    failures = [n for n, ok, _ in results if not ok]
    print(f"\nсценариев: {len(results) - len(failures)}/{len(results)} PASS")
    if strict and failures:
        print(f"FAILED: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())