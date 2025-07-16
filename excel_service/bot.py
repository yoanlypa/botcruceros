import asyncio, logging, math, datetime as _dt, pandas as _pd
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

from .parser import parse_excel
from .config import settings
from .exceptions import ParseError, ApiError
from .client import ApiClient

log = logging.getLogger("excel_bot")
logging.basicConfig(level=logging.INFO)

# ────────────── helpers ───────────────────────────────────────
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

# ────────────── handlers ──────────────────────────────────────
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

    # Descarga del archivo
    tg_file = await doc.get_file()
    content = bytes(await tg_file.download_as_bytearray())

    try:
        data = parse_excel(content)

        # Combinar metadatos con cada maleta
        pedidos = [
            sanitize({**data["general"], **m})
            for m in data["maletas"]
        ]

        resp = await ApiClient().post_pedidos(pedidos)
        await update.message.reply_text(
                f"✅ Creados: {resp['created']} · Actualizados: {resp['updated']}"
            )

    except ParseError as e:
        await update.message.reply_text(f"❌ Parseo: {e}")
    except ApiError as e:
        # recortar mensaje si es muy largo
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

# ────────────── arranque del bot ──────────────────────────────
async def run_bot_async():
    if not settings.tg_token:
        log.warning("TG_TOKEN no definido: el bot no se iniciará.")
        return

    app = ApplicationBuilder().token(settings.tg_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.add_error_handler(error_handler)

    await app.initialize()
    await app.start()        # inicia polling SIN instalar señales
    log.info("Telegram bot started")
