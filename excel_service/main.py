from fastapi import FastAPI, UploadFile, File, HTTPException
from .parser import parse_excel
from .config import settings
from .exceptions import ParseError, ApiError
from .client import ApiClient
import threading
from excel_service.bot import run_bot_async
import asyncio

app = FastAPI(title="Excel Supplier Microservice")

@app.post("/upload_excel")
async def upload_excel(file: UploadFile = File(...)):
    content = await file.read()
    try:
        data = parse_excel(content)
        # cada maleta se guarda como un pedido independiente
        pedidos = [m | data['general'] for m in data['maletas']]
        result = await ApiClient().post_pedidos(pedidos)
        return {"detail": f"Creado {len(pedidos)}", "backend": result}
    except ParseError as e:
        raise HTTPException(400, str(e))
    except ApiError as e:
        raise HTTPException(502, str(e))

# ---- Bot en background (opcional) ----
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_bot_async())

if settings.tg_token:        # solo arranca si tienes token
    import threading
    threading.Thread(target=lambda: asyncio.run(run_bot_async()), daemon=True).start()
