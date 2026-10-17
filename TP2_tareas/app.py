"""API HTTP y ciclo de vida: clases 19–21."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .gestor import Gestor, SinCapacidad
from .modelos import Configuracion, Estado, Solicitud


def crear_app(config=None):
    configuracion = config or Configuracion.desde_entorno()

    @asynccontextmanager
    async def ciclo(app):
        gestor = Gestor(configuracion)
        app.state.gestor = gestor
        await gestor.iniciar()
        try:
            yield
        finally:
            await gestor.cerrar()

    app = FastAPI(title='TP2 · Plataforma de tareas', lifespan=ciclo)

    def obtener(ident):
        if ident not in app.state.gestor.tareas:
            raise HTTPException(404, 'No existe esa tarea')
        return app.state.gestor.tareas[ident]

    @app.post('/tareas', status_code=201)
    async def crear(pedido: Solicitud):
        try:
            return app.state.gestor.crear(pedido)
        except (SinCapacidad, asyncio.QueueFull) as exc:
            raise HTTPException(503, 'Sin capacidad para aceptar tareas') from exc

    @app.get('/tareas')
    async def listar(estado: Estado | None = None):
        return [t.copy() for t in app.state.gestor.tareas.values()
                if estado is None or t['estado'] == estado]

    @app.get('/tareas/{ident}')
    async def consultar(ident: str):
        return obtener(ident).copy()

    @app.delete('/tareas/{ident}')
    async def cancelar(ident: str):
        if obtener(ident)['estado'] in ('completada', 'fallida'):
            raise HTTPException(409, 'La tarea ya terminó')
        return await app.state.gestor.cancelar(ident)

    @app.get('/estadisticas')
    async def estadisticas():
        return app.state.gestor.estadisticas()

    return app


app = crear_app()
