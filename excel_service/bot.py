# excel_service/bot.py

import os
import math
import logging
import datetime as _dt
from io import BytesIO
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.enums import ContentType
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

from excel_service.parser import parse_excel
from excel_service.client import ApiClient
from excel_service.exceptions import ParseError, ApiError
import pandas as _pd

import threading
import http.server
import socketserver
import asyncio

# ─────── Configuración ───────
load_dotenv()
TOKEN = os.getenv("TG_TOKEN")
MAX_SIZE_MB = int(os.getenv("MAX_SIZE_MB", 10))
ALLOWED_USERS = [6529038645]  # 👈 Reemplaza con tu ID de Telegram

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("excel_bot")

# ─────── Sanitizador ───────
def sanitize(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and math.isnan(v):
            out[k] = None
        elif isinstance(v, (_dt.datetime, _dt.date, _pd.Timestamp)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out

# ─────── Bot y Router ───────
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
@router.message(F.text == "/id")
async def cmd_id(message: Message):
    await message.reply(f"🆔 Tu user_id es: <code>{message.from_user.id}</code>")

@router.message(F.text == "/start")
async def start_cmd(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return await message.reply("⛔ No tienes permiso para usar este bot.")
    await message.reply("👋 Envíame un Excel 'Supplier Confirmation' y lo procesaré.")

@router.message(F.content_type == ContentType.DOCUMENT)
async def handle_document(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return await message.reply("⛔ No tienes permiso para usar este bot.")

    doc = message.document
    if not doc.file_name.lower().endswith(".xlsx"):
        return

    if doc.file_size and doc.file_size > MAX_SIZE_MB * 1024 * 1024:
        await message.reply("❌ Archivo demasiado grande.")
        return

    tgfile = await bot.get_file(doc.file_id)
    content_bytes = (await bot.download_file(tgfile.file_path)).read()

    try:
        data = parse_excel(content_bytes)
        pedidos = [sanitize({**data["general"], **m}) for m in data["maletas"]]
        resp = await ApiClient().post_pedidos(pedidos)

        msg = (
            f"✅ Creados: <b>{resp['created']}</b> · "
            f"Sobre-escritos: <b>{resp.get('overwritten',0)}</b>"
        )
        if resp.get("blocked"):
            msg += (
                f"\n⚠️ Grupos bloqueados por estado <i>final</i>: "
                f"<b>{resp['blocked']}</b>"
            )
            await message.reply(msg)

    except ParseError as e:
        await message.reply_document(
            document=BytesIO(content_bytes),
            filename=f"ERROR_{doc.file_name}",
            caption=f"❌ Parseo: {e}",
        )
    except ApiError as e:
        txt = str(e)
        if "final ya confirmado" in txt or "bloqueado" in txt:
            await message.reply(
                "⚠️ Algunos registros estaban cerrados en estado <b>final</b> y el Excel venía como <i>preliminary</i>."
            )
        else:
            if len(txt) > 400:
                txt = txt[:400] + "…"
            await message.reply(f"❌ Error de API:\n{txt}")
    except Exception:
        log.exception("Error inesperado")
        await message.reply("❌ Error inesperado procesando el archivo.")

# ---------- Health check para Railway ----------
def _health_server():
    port = int(os.getenv("PORT", 8080))
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args): ...
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    socketserver.TCPServer(("0.0.0.0", port), Handler).serve_forever()
threading.Thread(target=_health_server, daemon=True).start()

# ---------- Main ----------
async def main():
    if not TOKEN:
        log.warning("TELEGRAM TOKEN no definido; el bot no se iniciará.")
        return
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("🤖 Bot listo.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
