import asyncio
import threading
import time
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from TP2_tareas.app import crear_app
from TP2_tareas.modelos import Configuracion


@pytest.fixture
def web():
    observado = {'activas': 0, 'pico': 0, 'terminadas': 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                observado['activas'] += 1
                observado['pico'] = max(observado['pico'], observado['activas'])
            try:
                time.sleep(0.2 if self.path != '/lenta' else 1)
                self.send_response(503 if self.path == '/error' else 200)
                cuerpo = 'año'.encode('utf-8')
                self.send_header('Content-Length', str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with lock:
                    observado['activas'] -= 1
                    observado['terminadas'] += 1

        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    servidor.daemon_threads = True
    hilo = threading.Thread(target=servidor.serve_forever)
    hilo.start()
    try:
        yield f'http://127.0.0.1:{servidor.server_port}', observado
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join()


@asynccontextmanager
async def cliente(tmp_path, **opciones):
    app = crear_app(Configuracion(directorio=tmp_path, cierre=0.1, **opciones))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as c:
            yield c


async def terminar(c, ident):
    async with asyncio.timeout(10):
        while True:
            t = (await c.get('/tareas/' + ident)).json()
            if t['estado'] in ('completada', 'fallida', 'cancelada'):
                return t
            await asyncio.sleep(0.01)


async def enviar(c, **pedido):
    r = await c.post('/tareas', json=pedido)
    assert r.status_code == 201
    return r.json()['id']


async def test_descargas_reales_conservan_resultados_y_limite_global(tmp_path, web):
    url, observado = web
    async with cliente(tmp_path, workers=2, descargas=2) as c:
        ids = [await enviar(c, tipo='descargar', urls=[url, url + '/error'])
               for _ in range(2)]
        resultados = [await terminar(c, i) for i in ids]
        assert observado['pico'] == 2
        assert observado['terminadas'] == 4
        for t in resultados:
            assert t['estado'] == 'completada'
            assert [r['estado_http'] for r in t['resultado']] == [200, 503]
            assert [r['bytes'] for r in t['resultado']] == [4, 4]
            assert all(r['segundos'] >= 0.19 for r in t['resultado'])


async def test_una_url_caida_no_pierde_la_descarga_valida(tmp_path, web):
    url, _ = web
    async with cliente(tmp_path) as c:
        ident = await enviar(c, tipo='descargar', urls=[url, 'http://127.0.0.1:1'])
        t = await terminar(c, ident)
        assert t['estado'] == 'completada'
        assert t['resultado'][0]['bytes'] == 4
        assert t['resultado'][1]['error']


async def test_hash_utf8_con_resultado_conocido(tmp_path):
    async with cliente(tmp_path) as c:
        ident = await enviar(c, tipo='hashear', texto='á', iteraciones=17)
        t = await terminar(c, ident)
        assert t['estado'] == 'completada'
        assert t['resultado']['hash'] == '8bdfe47e81775c6e78469795ce2975796b47aabbef4363031d7d64fed1a0e3e3'


@pytest.mark.parametrize('tipo', ['hashear', 'descargar'])
@pytest.mark.parametrize('motivo', ['cancelacion', 'timeout'])
async def test_detener_operacion_y_reutilizar_worker(tmp_path, web, tipo, motivo):
    url, _ = web
    async with cliente(tmp_path, workers=1, procesos=1, lote_hash=10_000) as c:
        pedido = ({'tipo': 'hashear', 'texto': 'x', 'iteraciones': 10_000_000}
                  if tipo == 'hashear' else {'tipo': tipo, 'urls': [url + '/lenta']})
        if motivo == 'timeout':
            pedido['timeout'] = 0.08
        ident = await enviar(c, **pedido)
        await asyncio.sleep(0.04)
        # La API debe responder mientras el trabajo continúa.
        inicio = time.perf_counter()
        assert (await c.get('/tareas')).status_code == 200
        assert time.perf_counter() - inicio < 0.2
        if motivo == 'cancelacion':
            r = await c.delete('/tareas/' + ident)
            assert r.json()['estado'] == 'cancelada'
        t = await terminar(c, ident)
        assert t['estado'] == ('cancelada' if motivo == 'cancelacion' else 'fallida')
        inicio_siguiente = time.perf_counter()
        siguiente = await enviar(c, tipo='hashear', texto='x', iteraciones=20)
        assert (await terminar(c, siguiente))['estado'] == 'completada'
        # Si el cálculo cancelado siguiera ocupando el único proceso, este
        # trabajo corto quedaría detrás de millones de iteraciones abandonadas.
        assert time.perf_counter() - inicio_siguiente < 0.5
        assert (await c.get('/estadisticas')).json()['workers_ocupados'] == 0
