from math import log
from pydantic_settings import BaseSettings
from pydantic import Field, HttpUrl

class Settings(BaseSettings):
    tg_token:   str | None = Field(None, env="TG_TOKEN")
    django_url: HttpUrl    = Field(..., env="DJANGO_URL")

    # Autenticación
    django_email: str | None = Field(None, env="DJANGO_EMAIL") # JWT con email
    django_pass:  str | None = Field(None, env="DJANGO_PASS")

    max_size_mb: int = Field(5, env="MAX_SIZE_MB")

    class Config:
        env_file = ".env"

settings = Settings()
# Validación de configuración
if not settings.django_url:
    log.warning("DJANGO_URL no definido.")
if settings.tg_token and not settings.django_email:
    log.warning("TG_TOKEN definido, pero DJANGO_EMAIL no. El bot no podrá autenticar.")
if settings.django_email and not settings.django_pass:
    log.warning("DJANGO_EMAIL definido, pero DJANGO_PASS no. El bot no podrá autenticar.")
if settings.django_pass and not settings.django_email:
    log.warning("DJANGO_PASS definido, pero DJANGO_EMAIL no. El bot no podrá autenticar.")  
if settings.max_size_mb <= 0:
    raise ValueError("MAX_SIZE_MB debe ser un entero positivo.")
if settings.max_size_mb > 100:
    log.warning("MAX_SIZE_MB es muy grande, considera reducirlo para evitar problemas de rendimiento.")
if settings.max_size_mb < 1:
    log.warning("MAX_SIZE_MB es muy pequeño, ajustando a 1MB.") 
    
    
    
    
    
    
    
    
    
    
    