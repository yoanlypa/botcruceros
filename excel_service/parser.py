import unicodedata as _ud
from io import BytesIO
import datetime as _dt
import pandas as pd

from .exceptions import ParseError

# -------------------------------------------------------------
# 1 · Helpers
# -------------------------------------------------------------
def _slug(text: str) -> str:
    """Texto ASCII sin espacios/tildes, en minúsculas."""
    text = _ud.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return "".join(ch for ch in text.lower() if ch.isalnum())

def _normalize(val):
    """Convierte NaN / fechas / strings a tipos JSON-compatibles."""
    if pd.isna(val) or str(val).lower() == "nan":
        return None
    if isinstance(val, (_dt.datetime, _dt.date, pd.Timestamp)):
        return val.date().isoformat() if hasattr(val, "date") else val.isoformat()
    try:
        return pd.to_datetime(val).date().isoformat()
    except Exception:
        return str(val)

# -------------------------------------------------------------
# 2 · Configuración multilingüe
# -------------------------------------------------------------
SHEET_CANDIDATES = [
    "Supplier Confirmation",
    "Confirmación proveedor",
]

# Metadatos: slug → nombre interno
META_ALIAS = {
    "printingdate":       "printing_date",
    "fechaimpresion":     "printing_date",
    "fechadeimpresion":   "printing_date",
    "fechalistado":       "printing_date",     # ← NUEVO

    "servicedate":        "service_date",
    "fechaservicio":      "service_date",
    "fechadeservicio":    "service_date",

    "supplier":           "supplier",
    "proveedor":          "supplier",

    "emergencycontact":   "emergency_contact",
    "contactodeemergencia":"emergency_contact",
    "contactoemergencia":   "emergency_contact",
    "ship":               "ship",
    "barco":              "ship",

    "status":            "status",        
    "state":             "status",        
    "estado":            "status",
    "terminal":           "terminal",
}

CANON_COLS = [
    "Sign",
    "Excursion local name",
    "Language",
    "Ad",
    "Arrival / Meeting time",
]

SLUG_TO_CANON = {
    _slug(c): c for c in CANON_COLS
}
SLUG_TO_CANON.update({
    "cartel":             "Sign",
    "letrero":            "Sign",
    "nombreexcursion":    "Excursion local name",
    "excursionnombrelocal":"Excursion local name",
    "idioma":             "Language",
    "ad":                 "Ad",
    "adultos":            "Ad",
    "horallegadaencuentro":"Arrival / Meeting time",
})

# -------------------------------------------------------------
# 3 · Lector principal
# -------------------------------------------------------------
def parse_excel(content: bytes) -> dict:
    # 1) Seleccionar hoja
    sheet_name = None
    for cand in SHEET_CANDIDATES:
        try:
            pd.read_excel(BytesIO(content), sheet_name=cand, nrows=1)
            sheet_name = cand
            break
        except ValueError:
            continue
    if sheet_name is None:
        with pd.ExcelFile(BytesIO(content)) as xls:
            for name in xls.sheet_names:
                slug = _slug(name)
                if "confirmacion" in slug and "proveedor" in slug:
                    sheet_name = name
                    break
    if sheet_name is None:
        raise ParseError("Hoja de confirmación de proveedor no encontrada.")

    # 2) Leer hoja completa (sin header)
    try:
        df_all = pd.read_excel(BytesIO(content), sheet_name=sheet_name, header=None)
    except Exception as e:
        raise ParseError(f"Lectura Excel: {e}")

    # 3) Cabecera (“Sign” en col A)
    sign_rows = df_all.index[df_all.iloc[:, 0].astype(str).str.strip().str.lower() == "sign"]
    if sign_rows.empty:
        raise ParseError("No se encontró la fila de cabecera 'Sign'.")
    header_idx = int(sign_rows[0])

    # 4) Metadatos
    meta_df = df_all.iloc[1:header_idx, :2]
    general = {}
    for k, v in meta_df.values:
        key_slug = _slug(k)
        canon = META_ALIAS.get(key_slug, key_slug)
        general[canon] = _normalize(v)
    general["type_servicio"] = "barco"

    # 5) Tabla de maletas
    bags = pd.read_excel(BytesIO(content), sheet_name=sheet_name, header=header_idx)

    # Renombrar columnas por slug
    col_map = {}
    for col in bags.columns:
        slug = _slug(col)
        if slug in SLUG_TO_CANON:
            col_map[col] = SLUG_TO_CANON[slug]
    bags.rename(columns=col_map, inplace=True)

    missing = [c for c in CANON_COLS if c not in bags.columns]
    if missing:
        raise ParseError(
            f"Faltan columnas: {missing}. "
            f"Columnas encontradas: {list(bags.columns)}"
        )

    bags = bags[bags["Sign"].notna()]

    # 6) Convertir filas
    maletas = []
    for _, row in bags.iterrows():
        try:
            ad_val = int(row["Ad"]) if not pd.isna(row["Ad"]) else 0
        except ValueError:
            raise ParseError(f"Valor 'Ad' inválido en Sign={row['Sign']}")

        raw_time = row["Arrival / Meeting time"]
        arrival = None if pd.isna(raw_time) else (
            str(raw_time) if isinstance(raw_time, str)
            else pd.to_datetime(raw_time).time().isoformat(timespec="minutes")
        )

        maletas.append({
            "sign":         str(row["Sign"]).strip(),
            "excursion":    str(row["Excursion local name"]).strip(),
            "language":     "" if pd.isna(row["Language"]) else str(row["Language"]).strip(),
            "pax":          ad_val,
            "arrival_time": arrival,
        })

    if not maletas:
        raise ParseError("El archivo no contiene maletas válidas.")

    return {"general": general, "maletas": maletas}