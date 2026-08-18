#!/usr/bin/env python3
"""MossVoice Telegram bot: offers a 'Call' button that opens the WebApp."""

import argparse
import logging
import os

from telegram import Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
# SECURITY FIX: httpx logs the full request URL at INFO, which contains the
# bot token (…/bot<TOKEN>/method) — bot.log used to store it in plaintext.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("moss-bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    webapp_url = context.bot_data.get("webapp_url", "")
    await update.message.reply_text(
        "MossVoice — телефонный агент на клонированном голосе.\n\n"
        "Нажмите «Позвонить», чтобы связаться с агентом:",
        reply_markup={
            "inline_keyboard": [[{
                "text": "\u260e Позвонить",
                "web_app": {"url": webapp_url},
            }]],
        },
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Этот бот открывает приложение звонка MossVoice.\n"
        "Нажмите «Позвонить» и разрешите доступ к микрофону."
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
