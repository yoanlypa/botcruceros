# excel_service/bot.py
# ------------------------------------------------------------
import asyncio
import datetime as _dt
import http.server
import logging
import math
import os
import socketserver
import threading
from io import BytesIO

import pandas as _pd
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from excel_service.config import settings           # ABSOLUTE import
from excel_service.parser import parse_excel
from excel_service.client import ApiClient
from excel_service.exceptions import ParseError, ApiError

log = logging.getLogger("excel_bot")
logging.basicConfig(level=logging.INFO)

# ────────────── helpers ─────────────────────────────────────
def sanitize(d: dict) -> dict:
    """Convierte NaN a None y datetime a ISO string para JSON."""
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and math.isnan(v):
            out[k] = None
        elif isinstance(v, (_dt.datetime, _dt.date, _pd.Timestamp)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out

# ────────────── handlers ───────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola. Envíame un Excel 'Supplier Confirmation' y lo procesaré."
    )

async def handle_doc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".xlsx"):
        return
    if doc.file_size and doc.file_size > settings.max_size_mb * 1024 * 1024:
        await update.message.reply_text("❌ Archivo demasiado grande.")
        return

    tg_file = await doc.get_file()
    content = bytes(await tg_file.download_as_bytearray())

    try:
        data = parse_excel(content)
        pedidos = [sanitize({**data["general"], **m}) for m in data["maletas"]]

        resp = await ApiClient().post_pedidos(pedidos)
        await update.message.reply_text(
            f"✅ Creados: {resp['created']} · Actualizados: {resp['updated']}"
        )

    except ParseError as e:
        await update.message.reply_document(
            document=BytesIO(content),
            filename=f"ERROR_{doc.file_name}",
            caption=f"❌ Parseo: {e}",
        )
    except ApiError as e:
        msg = str(e)
        if len(msg) > 400:
            msg = msg[:400] + "…"
        await update.message.reply_text(f"❌ API: {msg}")
    except Exception as e:
        log.exception(e)
        await update.message.reply_text("❌ Error inesperado.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Telegram handler error:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ Error interno.")

# ────────────── health check (Railway) ──────────────────────
def _health_server():
    port = int(os.getenv("PORT", 8080))
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silencia log HTTP
            return
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    socketserver.TCPServer(("0.0.0.0", port), Handler).serve_forever()

threading.Thread(target=_health_server, daemon=True).start()

# ────────────── arranque principal ─────────────────────────
async def run_bot_async():
    if not settings.tg_token:
        log.warning("TG_TOKEN no definido: el bot no se iniciará.")
        return

    app = ApplicationBuilder().token(settings.tg_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.add_error_handler(error_handler)

    log.info("Starting bot with token prefix %s…", settings.tg_token[:8])

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()      # mantiene vivo hasta Ctrl-C / SIGTERM

if __name__ == "__main__":
    asyncio.run(run_bot_async())
