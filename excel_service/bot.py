import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from excel_service import parser
from excel_service.client import ApiClient
from tempfile import NamedTemporaryFile

# --- Configuración de logs ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Bot y Dispatcher ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN no está configurado en el entorno")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# --- Lista de usuarios autorizados (puedes añadir más) ---
ALLOWED_USERS = [123456789]  # Reemplaza con tu user_id de Telegram

# --- Utilidad para saber si un mensaje es válido ---
def is_authorized(user_id):
    return user_id in ALLOWED_USERS

# --- Handler para documentos Excel ---
@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        await message.reply("⛔ No tienes permiso para usar este bot.")
        logger.warning(f"Usuario no autorizado: {user_id}")
        return

    doc = message.document
    if not doc.file_name.endswith(".xlsx"):
        await message.reply("❌ Solo se aceptan archivos .xlsx")
        return

    # Descargar el archivo
    file = await bot.get_file(doc.file_id)
    file_path = file.file_path
    content = await bot.download_file(file_path)

    with NamedTemporaryFile(suffix=".xlsx", delete=True) as tmp:
        tmp.write(content.read())
        tmp.flush()

        try:
            # Parsear y convertir en pedidos
            data = parser.parse_excel(tmp.name)
            pedidos = [parser.sanitize({**data["general"], **m}) for m in data["maletas"]]

            # Enviar pedidos a API
            api = ApiClient()
            response = await api.post_pedidos(pedidos)

            # Mensaje de éxito
            msg = "✅ Pedidos recibidos correctamente."
            if response and isinstance(response, dict):
                if "sobrescritos" in response:
                    msg += f"\n📝 Se sobrescribieron datos anteriores para {response['sobrescritos']} barco/fecha."
                if "created" in response:
                    msg += f"\n📦 Nuevos pedidos creados: {response['created']}."
            await message.reply(msg)

        except Exception as e:
            logger.exception("Error procesando el Excel")
            await message.reply("❌ Error procesando el archivo. Revisa que esté bien formateado.")

# --- Comando /start ---
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    if not is_authorized(message.from_user.id):
        return await message.reply("⛔ No tienes permiso para usar este bot.")
    await message.reply("👋 Bot activo y esperando archivos .xlsx")

# --- Inicio del bot ---
if __name__ == "__main__":
    logger.info("🤖 Bot iniciado correctamente.")
    executor.start_polling(dp, skip_updates=True)
