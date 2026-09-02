#!/usr/bin/env python3
"""MossVoice Telegram bot: Call WebApp + household bind deep-link (E6)."""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, WebAppInfo  # noqa: E402
from telegram.ext import Application, CommandHandler, ContextTypes  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("moss-bot")


def _try_bind(update: Update, start_arg: str) -> str | None:
    """If ``/start bind_<token>``, store telegram contact. Return status text."""
    from core.tg_bind import parse_start_payload, verify_bind_token

    token = parse_start_payload(start_arg) if start_arg else None
    if not token and start_arg and start_arg.startswith("bind_"):
        token = start_arg[len("bind_"):]
    if not token:
        return None
    household_id = verify_bind_token(token)
    if not household_id:
        return "Ссылка привязки недействительна или истекла."
    chat_id = str(update.effective_chat.id)
    try:
        from adapters.pg import maybe_pg_store
        import uuid
        pg = maybe_pg_store(check=False)
        if not getattr(pg, "available", False):
            return "База временно недоступна. Попробуйте позже."
        cid = "ct-" + uuid.uuid4().hex[:12]
        pg._exec(
            "INSERT INTO contacts (id, household_id, channel, address, "
            "escalate_order, label) VALUES (%s, %s, 'telegram', %s, 0, %s)",
            (cid, household_id, chat_id,
             (update.effective_user.full_name if update.effective_user
              else "") or "telegram"))
        return ("Telegram привязан к семье. Тревоги будут приходить сюда. "
                "Спасибо.")
    except Exception as e:  # noqa: BLE001
        log.exception("bind failed: %s", e)
        return "Не удалось сохранить привязку. Напишите в поддержку."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_arg = " ".join(context.args) if context.args else ""
    # Also accept payload glued to /start without space via message text.
    if not start_arg and update.message and update.message.text:
        parts = update.message.text.split(maxsplit=1)
        if len(parts) > 1:
            start_arg = parts[1]
    bind_msg = _try_bind(update, start_arg)
    if bind_msg:
        await update.message.reply_text(bind_msg)
        return

    webapp_url = context.bot_data.get("webapp_url", "")
    await update.message.reply_text(
        "IMVERA — забота о близких по телефону.\n\n"
        "Нажмите «Позвонить», чтобы связаться с Верой:",
        reply_markup={
            "inline_keyboard": [[{
                "text": "\u260e Позвонить",
                "web_app": {"url": webapp_url},
            }]],
        },
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "IMVERA: откройте «Позвонить» для голосового звонка Веры.\n"
        "Привязка уведомлений: отсканируйте QR из приложения семьи."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("MOSSVOICE_BOT_TOKEN", ""))
    ap.add_argument("--webapp-url", required=True,
                    help="HTTPS URL of the WebApp (cloudflared tunnel or deployed page)")
    ap.add_argument("--port", type=int, default=8601)
    args = ap.parse_args()

    if not args.token:
        print("ERROR: no --token (or MOSSVOICE_BOT_TOKEN env)", flush=True)
        return

    app = Application.builder().token(args.token).build()
    app.bot_data["webapp_url"] = args.webapp_url
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    log.info("polling... webapp=%s", args.webapp_url)
    app.run_polling()


if __name__ == "__main__":
    main()
