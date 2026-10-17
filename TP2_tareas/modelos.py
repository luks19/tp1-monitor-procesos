"""Pedidos validados y configuración de arranque (clase 19)."""
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Estado = Literal['pendiente', 'ejecutando', 'completada', 'fallida', 'cancelada']


class Pedido(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    timeout: float = Field(default=30, gt=0, le=3600)


class Esperar(Pedido):
    tipo: Literal['esperar']
    segundos: float = Field(ge=0, le=3600)


class Hashear(Pedido):
    tipo: Literal['hashear']
    texto: str = Field(min_length=1, max_length=100_000)
    iteraciones: int = Field(ge=1, le=100_000_000)


class Descargar(Pedido):
    tipo: Literal['descargar']
    urls: list[HttpUrl] = Field(min_length=1, max_length=100)


Solicitud = Annotated[Esperar | Hashear | Descargar, Field(discriminator='tipo')]


class Configuracion(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    workers: int = Field(default=4, ge=1, le=64)
    capacidad: int = Field(default=100, ge=1, le=10_000)
    procesos: int = Field(default=2, ge=1, le=32)
    descargas: int = Field(default=20, ge=1, le=100)
    lote_hash: int = Field(default=100_000, ge=1000, le=1_000_000)
    cierre: float = Field(default=3, gt=0, le=60)
    directorio: Path = Path('estado')

    @classmethod
    def desde_entorno(cls):
        return cls(**{nombre: os.environ[f'TP2_{nombre.upper()}']
                      for nombre in cls.model_fields
                      if f'TP2_{nombre.upper()}' in os.environ})
