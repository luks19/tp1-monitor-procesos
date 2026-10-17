"""Productor-consumidor con asyncio: clases 11 y 21."""
import asyncio
import json
import logging
import time
from collections import Counter
from uuid import uuid4

from .modelos import Configuracion, Pedido

log = logging.getLogger(__name__)
CENTINELA = object()
TERMINALES = {'completada', 'fallida', 'cancelada'}
ESTADOS = ('pendiente', 'ejecutando', 'completada', 'fallida', 'cancelada')


class SinCapacidad(Exception):
    """La aplicación no puede aceptar trabajo nuevo."""


class Gestor:
    def __init__(self, config: Configuracion):
        self.config = config
        self.cola = asyncio.Queue(maxsize=config.capacidad)
        self.tareas = {}
        self.activas = {}
        self.workers = []
        self.aceptando = False

    async def iniciar(self):
        self.config.directorio.mkdir(parents=True, exist_ok=True)
        previos = sorted(self.config.directorio.glob('estado_*.json'))
        if previos:
            log.info('Volcado previo encontrado: %s (no se restaura)', previos[-1])
        self.workers = [asyncio.create_task(self._worker(), name=f'worker-{i}')
                        for i in range(self.config.workers)]
        self.aceptando = True

    def crear(self, pedido: Pedido):
        if not self.aceptando:
            raise SinCapacidad('Servidor cerrando')
        identificador = uuid4().hex
        # No hay await entre registrar y encolar: mismo hilo/event loop.
        self.cola.put_nowait((identificador, pedido))
        tarea = {
            'id': identificador, 'tipo': pedido.tipo, 'estado': 'pendiente',
            'parametros': pedido.model_dump(mode='json'), 'creada': time.time(),
            'iniciada': None, 'finalizada': None, 'espera_cola': None,
            'duracion': None, 'resultado': None, 'error': None,
        }
        self.tareas[identificador] = tarea
        return tarea.copy()

    async def _worker(self):
        while True:
            item = await self.cola.get()
            try:
                if item is CENTINELA:
                    return
                ident, pedido = item
                if self.tareas[ident]['estado'] == 'cancelada':
                    continue
                operacion = asyncio.create_task(self._procesar(ident, pedido),
                                               name=f'tarea-{ident}')
                self.activas[ident] = operacion
                try:
                    await operacion
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                finally:
                    self.activas.pop(ident, None)
            finally:
                self.cola.task_done()

    async def _ejecutar(self, pedido):
        if pedido.tipo == 'esperar':
            await asyncio.sleep(pedido.segundos)
            return {'segundos': pedido.segundos}
        raise ValueError('Operación todavía no implementada')

    async def _procesar(self, ident, pedido):
        tarea = self.tareas[ident]
        inicio = time.perf_counter()
        tarea.update(estado='ejecutando', iniciada=time.time())
        tarea['espera_cola'] = tarea['iniciada'] - tarea['creada']
        try:
            async with asyncio.timeout(pedido.timeout):
                resultado = await self._ejecutar(pedido)
            tarea.update(estado='completada', resultado=resultado)
        except TimeoutError:
            tarea.update(estado='fallida', error=f'Timeout de tarea: {pedido.timeout}s')
        except asyncio.CancelledError:
            tarea.update(estado='cancelada', error=None)
            raise
        except Exception as exc:
            tarea.update(estado='fallida', error=f'{type(exc).__name__}: {exc}')
            log.exception('Falló la tarea %s', ident)
        finally:
            tarea.update(finalizada=time.time(), duracion=time.perf_counter() - inicio)

    async def cancelar(self, ident):
        tarea = self.tareas[ident]
        if tarea['estado'] in TERMINALES:
            return tarea.copy()
        operacion = self.activas.get(ident)
        if operacion:
            if not operacion.cancelling():
                operacion.cancel()
            try:
                await asyncio.shield(operacion)
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
        else:
            tarea.update(estado='cancelada', finalizada=time.time())
        return tarea.copy()

    def estadisticas(self):
        conteo = Counter(t['estado'] for t in self.tareas.values())
        duraciones = [t['duracion'] for t in self.tareas.values()
                      if t['duracion'] is not None]
        esperas = [t['espera_cola'] for t in self.tareas.values()
                   if t['espera_cola'] is not None]
        return {
            'total': len(self.tareas),
            'por_estado': {estado: conteo[estado] for estado in ESTADOS},
            'workers_ocupados': sum(not t.done() for t in self.activas.values()),
            'workers': self.config.workers,
            'entradas_en_cola': self.cola.qsize(),
            'promedio_ejecucion': sum(duraciones) / len(duraciones) if duraciones else 0,
            'promedio_espera_cola': sum(esperas) / len(esperas) if esperas else 0,
        }

    async def cerrar(self):
        self.aceptando = False
        try:
            async with asyncio.timeout(self.config.cierre):
                await self.cola.join()
        except TimeoutError:
            log.info('Plazo de cierre agotado; cancelando trabajo restante')
            await asyncio.gather(*(self.cancelar(i) for i in self.tareas
                                   if self.tareas[i]['estado'] not in TERMINALES))
            await self.cola.join()
        for _ in self.workers:
            await self.cola.put(CENTINELA)
        await asyncio.gather(*self.workers)
        destino = self.config.directorio / f'estado_{time.time_ns()}.json'
        temporal = destino.with_suffix('.tmp')
        temporal.write_text(json.dumps(list(self.tareas.values()), indent=2,
                                       ensure_ascii=False), encoding='utf-8')
        temporal.replace(destino)
        log.info('Estado guardado: %s', destino)
