import asyncio
import time

import httpx
import pytest


@pytest.fixture
async def cliente(tmp_path):
    from TP2_tareas.app import crear_app
    from TP2_tareas.modelos import Configuracion

    app = crear_app(Configuracion(workers=1, capacidad=1, directorio=tmp_path,
                                 cierre=0.1))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as c:
            yield c


async def estado_final(c, identificador):
    async with asyncio.timeout(5):
        while True:
            tarea = (await c.get(f'/tareas/{identificador}')).json()
            if tarea['estado'] in ('completada', 'fallida', 'cancelada'):
                return tarea
            await asyncio.sleep(0.01)


async def crear(c, segundos=0.03, **campos):
    r = await c.post('/tareas', json={'tipo': 'esperar', 'segundos': segundos,
                                    **campos})
    assert r.status_code == 201
    return r.json()['id']


async def test_post_responde_antes_de_terminar_y_luego_publica_resultado(cliente):
    inicio = time.perf_counter()
    ident = await crear(cliente, segundos=0.25)
    assert time.perf_counter() - inicio < 0.2
    primera = (await cliente.get(f'/tareas/{ident}')).json()
    assert primera['estado'] in ('pendiente', 'ejecutando')
    final = await estado_final(cliente, ident)
    assert final['estado'] == 'completada'
    assert final['resultado'] == {'segundos': 0.25}
    assert final['duracion'] >= 0.24


@pytest.mark.parametrize('datos', [
    {'tipo': 'esperar', 'segundos': -1},
    {'tipo': 'esperar', 'segundos': 1, 'timeout': 0},
    {'tipo': 'hashear', 'texto': 'x', 'iteraciones': 0},
    {'tipo': 'descargar', 'urls': []},
    {'tipo': 'descargar', 'urls': ['file:///etc/passwd']},
    {'tipo': 'volar'},
])
async def test_rechaza_trabajo_invalido_sin_registrarlo(cliente, datos):
    assert (await cliente.post('/tareas', json=datos)).status_code == 422
    assert (await cliente.get('/tareas')).json() == []


async def test_consulta_y_cancelacion_de_id_inexistente(cliente):
    assert (await cliente.get('/tareas/no-existe')).status_code == 404
    assert (await cliente.delete('/tareas/no-existe')).status_code == 404


async def test_cola_llena_no_deja_tarea_fantasma(cliente):
    activa = await crear(cliente, 10)
    await asyncio.sleep(0.02)
    pendiente = await crear(cliente, 10)
    assert (await cliente.post('/tareas', json={
        'tipo': 'esperar', 'segundos': 1})).status_code == 503
    assert len((await cliente.get('/tareas')).json()) == 2
    assert (await cliente.delete(f'/tareas/{pendiente}')).json()['estado'] == 'cancelada'
    assert (await cliente.delete(f'/tareas/{activa}')).json()['estado'] == 'cancelada'
    await asyncio.sleep(0.02)
    nueva = await crear(cliente)
    assert (await estado_final(cliente, nueva))['estado'] == 'completada'


async def test_timeout_no_mata_al_worker(cliente):
    ident = await crear(cliente, 10, timeout=0.03)
    final = await estado_final(cliente, ident)
    assert final['estado'] == 'fallida'
    assert 'timeout' in final['error'].lower()
    siguiente = await crear(cliente)
    assert (await estado_final(cliente, siguiente))['estado'] == 'completada'


async def test_cancelacion_repetida_y_estadisticas_consistentes(cliente):
    ident = await crear(cliente, 10)
    await asyncio.sleep(0.02)
    for _ in range(2):
        r = await cliente.delete(f'/tareas/{ident}')
        assert r.status_code == 200
        assert r.json()['estado'] == 'cancelada'
    completada = await crear(cliente)
    await estado_final(cliente, completada)
    assert (await cliente.delete(f'/tareas/{completada}')).status_code == 409
    assert len((await cliente.get('/tareas?estado=cancelada')).json()) == 1
    stats = (await cliente.get('/estadisticas')).json()
    assert stats['por_estado'] == {'pendiente': 0, 'ejecutando': 0,
                                  'completada': 1, 'fallida': 0, 'cancelada': 1}
    assert stats['workers_ocupados'] == 0
