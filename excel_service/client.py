"""
Cliente HTTP para tu backend:
• Si DJANGO_KEY está definido  → TokenAuthentication
• Si DJANGO_EMAIL / DJANGO_PASS → obtiene JWT (Simple JWT) en /api/token/
"""

import httpx, datetime as dt
from .config import settings
from .exceptions import ApiError

class ApiClient:
    def __init__(self):
        # cast a str → ya tiene rstrip
        self.base = str(settings.django_url).rstrip("/") + "/api"
        self.cli = httpx.AsyncClient(timeout=20)
        self.headers: dict[str, str] = {}
        self._jwt_exp: dt.datetime | None = None
        if settings.django_email and settings.django_pass:
            # Si tienes email y pass, usa JWT
            self.headers["Authorization"] = f"Bearer {settings.django_email}:{settings.django_pass}"
        # cliente httpx único
        self.cli = httpx.AsyncClient(
            base_url=self.base,
            headers=self.headers,
            timeout=10
        )

    # ---------- JWT helpers ----------
    async def _login_jwt(self):
        email = settings.django_email
        pwd   = settings.django_pass
        if not (email and pwd):
            raise ApiError("Faltan DJANGO_EMAIL / DJANGO_PASS en .env")

        resp = await self.cli.post("/token/", json={"email": email, "password": pwd})
        if resp.status_code != 200:
            raise ApiError(f"Login JWT {resp.status_code}: {resp.text}")

        access = resp.json()["access"]
        self.headers["Authorization"] = f"Bearer {access}"
        self.cli.headers.update(self.headers)
        self._jwt_exp = dt.datetime.utcnow() + dt.timedelta(minutes=25)

    async def _ensure_jwt(self):
        if (self._jwt_exp is None) or (self._jwt_exp <= dt.datetime.utcnow()):
            await self._login_jwt()

    async def post_pedidos(self, pedidos: list[dict]) -> dict:
        """
        Envía la lista completa a /pedidos/cruceros/bulk/.
        El backend la procesa en lote.
        """
        await self._ensure_jwt()
        resp = await self.cli.post("/pedidos/cruceros/bulk/", json=pedidos)
        if resp.status_code >= 400:
            raise ApiError(f"Backend {resp.status_code}: {resp.text}")
        return resp.json()