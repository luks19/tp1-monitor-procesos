"""Tres experimentos del TP2. Ejecutar desde la raíz con -m.

La API bloqueante es una referencia deliberadamente incorrecta y aislada:
no forma parte de la aplicación que levanta Docker Compose.
"""
import argparse
import asyncio
import json
import os
import platform
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI

from .modelos import Hashear
from .tareas import hash_lote

# Referencia mínima: misma operación SHA-256 y consulta GET /tareas,
# pero el cálculo ocurre dentro del loop, sin executor.
api_bloqueante = FastAPI(title='Solo medición: loop bloqueado')
_referencia = {}
_en_curso = set()


@api_bloqueante.post('/tareas', status_code=201)
async def crear_referencia(pedido: Hashear):
    ident = uuid4().hex
    registro = {'id': ident, 'estado': 'pendiente'}
    _referencia[ident] = registro

    async def calcular():
        registro['estado'] = 'ejecutando'
        digest = hash_lote(pedido.texto.encode('utf-8'), pedido.iteraciones)
        registro.update(estado='completada', resultado=digest.hex())

    tarea = asyncio.create_task(calcular())
    _en_curso.add(tarea)
    tarea.add_done_callback(_en_curso.discard)
    return registro.copy()


@api_bloqueante.get('/tareas')
async def listar_referencia():
    return list(_referencia.values())


@contextmanager
def api(config, bloqueante=False):
    """Cliente y servidor viven en procesos distintos, como en clase 19."""
    with socket.socket() as reserva:
        reserva.bind(('127.0.0.1', 0))
        puerto = reserva.getsockname()[1]
    modulo = ('TP2_tareas.mediciones:api_bloqueante' if bloqueante
              else 'TP2_tareas.app:app')
    with tempfile.TemporaryDirectory(prefix='tp2-medicion-') as temporal:
        env = {**os.environ, 'TP2_WORKERS': str(config.workers),
               'TP2_PROCESOS': str(config.procesos), 'TP2_CAPACIDAD': '10000',
               'TP2_DESCARGAS': '20', 'TP2_DIRECTORIO': temporal}
        with tempfile.TemporaryFile(mode='w+') as salida:
            proceso = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', modulo, '--host', '127.0.0.1',
                 '--port', str(puerto), '--log-level', 'warning'],
                env=env, stdout=salida, stderr=subprocess.STDOUT,
                start_new_session=True)
            base = f'http://127.0.0.1:{puerto}'
            try:
                limite = time.monotonic() + 15
                with httpx.Client(timeout=0.2, trust_env=False) as c:
                    while True:
                        try:
                            if c.get(base + '/tareas').status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if proceso.poll() is not None or time.monotonic() > limite:
                            salida.seek(0)
                            raise RuntimeError('API no arrancó: ' + salida.read())
                        time.sleep(0.03)
                yield base
            finally:
                proceso.terminate()
                try:
                    proceso.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proceso.pid, signal.SIGKILL)
                    proceso.wait(timeout=3)


@contextmanager
def web(demora):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(demora)
            cuerpo = b'x' * 1024
            self.send_response(200)
            self.send_header('Content-Length', str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    class Servidor(ThreadingHTTPServer):
        request_queue_size = 128
        daemon_threads = True

    servidor = Servidor(('127.0.0.1', 0), Handler)
    hilo = threading.Thread(target=servidor.serve_forever)
    hilo.start()
    try:
        yield f'http://127.0.0.1:{servidor.server_port}/dato'
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join()


async def enviar(cliente, pedido):
    respuesta = await cliente.post('/tareas', json=pedido)
    respuesta.raise_for_status()
    return respuesta.json()['id']


async def esperar(cliente, ids):
    async with asyncio.timeout(120):
        while True:
            respuesta = await cliente.get('/tareas')
            respuesta.raise_for_status()
            tareas = {t['id']: t for t in respuesta.json()}
            if all(tareas[i]['estado'] in ('completada', 'fallida', 'cancelada')
                   for i in ids):
                return [tareas[i] for i in ids]
            await asyncio.sleep(0.01)


async def medir_io(base, url):
    async with httpx.AsyncClient(timeout=30, trust_env=False) as descargas:
        inicio = time.perf_counter()
        respuestas = [await descargas.get(url) for _ in range(20)]
        secuencial = time.perf_counter() - inicio
    async with httpx.AsyncClient(base_url=base, timeout=30, trust_env=False) as c:
        inicio = time.perf_counter()
        ident = await enviar(c, {'tipo': 'descargar', 'urls': [url] * 20})
        tarea = (await esperar(c, [ident]))[0]
        concurrente = time.perf_counter() - inicio
    return {'descargas': 20, 'bytes_por_respuesta': 1024,
            'exitosas_secuenciales': sum(r.status_code == 200 for r in respuestas),
            'exitosas_concurrentes': sum(r['estado_http'] == 200 and r['error'] is None
                                         for r in tarea['resultado']),
            'secuencial_segundos': secuencial, 'concurrente_segundos': concurrente,
            'speedup': secuencial / concurrente}


async def medir_cpu(base, iteraciones):
    async with httpx.AsyncClient(base_url=base, timeout=60, trust_env=False) as c:
        calentamiento = await enviar(c, {'tipo': 'hashear', 'texto': 'x',
                                        'iteraciones': 1000})
        await esperar(c, [calentamiento])  # excluye arranque del primer proceso
        inicio = time.perf_counter()
        ident = await enviar(c, {'tipo': 'hashear', 'texto': 'x',
                                'iteraciones': iteraciones})
        await asyncio.sleep(0.02)
        consulta = time.perf_counter()
        r = await c.get('/tareas')
        r.raise_for_status()
        latencia = time.perf_counter() - consulta
        final = (await esperar(c, [ident]))[0]
        return {'get_segundos': latencia, 'total_segundos': time.perf_counter() - inicio,
                'estado': final['estado']}


def p95(valores):
    ordenados = sorted(valores)
    # Percentil por rango más cercano, declarado para reproducirlo.
    import math
    return ordenados[max(0, math.ceil(0.95 * len(ordenados)) - 1)]


async def medir_pool(base, config):
    filas = []
    async with httpx.AsyncClient(base_url=base, timeout=120, trust_env=False) as c:
        warm = await asyncio.gather(*(enviar(c, {
            'tipo': 'hashear', 'texto': 'x', 'iteraciones': 1000})
            for _ in range(config.procesos)))
        await esperar(c, warm)
        for cantidad in config.cantidades:
            inicio = time.perf_counter()
            ids = await asyncio.gather(*(enviar(c, {
                'tipo': 'hashear', 'texto': 'x', 'iteraciones': config.iteraciones,
                'timeout': 120}) for _ in range(cantidad)))
            tareas = await esperar(c, ids)
            total = time.perf_counter() - inicio
            esperas = [t['espera_cola'] for t in tareas if t['espera_cola'] is not None]
            duraciones = [t['duracion'] for t in tareas if t['duracion'] is not None]
            latencias = [t['espera_cola'] + t['duracion'] for t in tareas
                         if t['duracion'] is not None]
            filas.append({
                'cantidad': cantidad, 'total_segundos': total,
                'completadas': sum(t['estado'] == 'completada' for t in tareas),
                'fallidas': sum(t['estado'] != 'completada' for t in tareas),
                'tareas_por_segundo': cantidad / total,
                'espera_cola_promedio': statistics.mean(esperas),
                'ejecucion_promedio': statistics.mean(duraciones),
                'latencia_p95': p95(latencias),
            })
    return {'lotes': filas}


def positivo(valor):
    n = int(valor)
    if n <= 0:
        raise argparse.ArgumentTypeError('Debe ser un entero positivo')
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('modo', choices=['io', 'cpu', 'pool'])
    parser.add_argument('--salida', type=Path)
    parser.add_argument('--workers', type=positivo, default=4)
    parser.add_argument('--procesos', type=positivo, default=2)
    parser.add_argument('--iteraciones', type=positivo, default=2_000_000)
    parser.add_argument('--cantidades', nargs='+', type=positivo, default=[4, 16, 64])
    parser.add_argument('--demora', type=float, default=0.1)
    config = parser.parse_args()
    if config.demora < 0:
        parser.error('--demora no puede ser negativa')
    resultado = {'modo': config.modo, 'fecha_utc': datetime.now(timezone.utc).isoformat(),
                 'entorno': {'python': platform.python_version(),
                             'sistema': platform.platform(), 'cpu_logicas': os.cpu_count()},
                 'workers': config.workers, 'procesos': config.procesos,
                 'iteraciones': config.iteraciones}
    if config.modo == 'io':
        with api(config) as base, web(config.demora) as url:
            resultado.update(asyncio.run(medir_io(base, url)))
        resultado['demora_http'] = config.demora
    elif config.modo == 'cpu':
        for bloqueante, nombre in [(True, 'sin_executor'), (False, 'con_executor')]:
            with api(config, bloqueante=bloqueante) as base:
                resultado[nombre] = asyncio.run(medir_cpu(base, config.iteraciones))
    else:
        with api(config) as base:
            resultado.update(asyncio.run(medir_pool(base, config)))
    destino = config.salida or Path('TP2_tareas/resultados') / f'{config.modo}.json'
    destino.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(resultado, indent=2, ensure_ascii=False)
    destino.write_text(contenido + '\n', encoding='utf-8')
    print(contenido)


if __name__ == '__main__':
    main()
