import asyncio
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from TP2_tareas.gestor import Gestor
from TP2_tareas.modelos import Configuracion, Esperar


async def test_cancelar_antes_de_que_empiece_el_cuerpo(tmp_path):
    gestor = Gestor(Configuracion(directorio=tmp_path, workers=1, cierre=0.05))
    await gestor.iniciar()
    try:
        ident = gestor.crear(Esperar(tipo='esperar', segundos=10))['id']
        await asyncio.sleep(0)  # el worker tomó el ítem, el trabajo aún puede no correr
        resultado = await gestor.cancelar(ident)
        assert resultado['estado'] == 'cancelada'
        assert resultado['finalizada'] is not None
    finally:
        await gestor.cerrar()


async def test_cierre_vuelca_pendientes_y_activas_y_rechaza_trabajo(tmp_path):
    from TP2_tareas.gestor import SinCapacidad

    gestor = Gestor(Configuracion(directorio=tmp_path, workers=1, cierre=0.05))
    await gestor.iniciar()
    for _ in range(3):
        gestor.crear(Esperar(tipo='esperar', segundos=10))
    await asyncio.sleep(0.01)
    inicio = time.perf_counter()
    await gestor.cerrar()
    assert time.perf_counter() - inicio < 1
    with pytest.raises(SinCapacidad):
        gestor.crear(Esperar(tipo='esperar', segundos=0))
    archivos = list(tmp_path.glob('estado_*.json'))
    assert len(archivos) == 1
    guardadas = json.loads(archivos[0].read_text())
    assert len(guardadas) == 3
    assert all(t['estado'] == 'cancelada' for t in guardadas)
    assert all(w.done() for w in gestor.workers)


async def test_arranque_informa_volcado_anterior(tmp_path, caplog):
    (tmp_path / 'estado_123.json').write_text('[]')
    with caplog.at_level(logging.INFO):
        gestor = Gestor(Configuracion(directorio=tmp_path))
        await gestor.iniciar()
        await gestor.cerrar()
    assert 'estado_123.json' in caplog.text
    assert 'no se restaura' in caplog.text


@pytest.mark.parametrize('senal', [signal.SIGTERM, signal.SIGINT])
def test_senal_real_cierra_servidor_y_persiste_estado(tmp_path, senal):
    # Proceso separado: el cliente sigue vivo aunque el event loop del servidor falle.
    previo = tmp_path / 'estado_previo.json'
    previo.write_text('[]')
    with socket.socket() as reserva:
        reserva.bind(('127.0.0.1', 0))
        puerto = reserva.getsockname()[1]
    env = {**os.environ, 'TP2_DIRECTORIO': str(tmp_path), 'TP2_CIERRE': '0.1'}
    raiz = Path(__file__).resolve().parents[2]
    with (tmp_path / 'servidor.log').open('w') as salida:
        proceso = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'TP2_tareas.app:app', '--host',
             '127.0.0.1', '--port', str(puerto), '--log-level', 'info'],
            cwd=raiz, env=env, stdout=salida, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{puerto}',
                              timeout=2, trust_env=False) as c:
                limite = time.monotonic() + 10
                while True:
                    try:
                        if c.get('/estadisticas').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > limite:
                        pytest.fail((tmp_path / 'servidor.log').read_text())
                    time.sleep(0.05)
                r = c.post('/tareas', json={'tipo': 'esperar', 'segundos': 10})
                ident = r.json()['id']
                time.sleep(0.05)
                inicio = time.perf_counter()
                proceso.send_signal(senal)
                proceso.wait(timeout=5)
                assert time.perf_counter() - inicio < 3
            assert 'estado_previo.json' in (tmp_path / 'servidor.log').read_text()
            volcados = [p for p in tmp_path.glob('estado_*.json') if p != previo]
            assert len(volcados) == 1
            tarea = next(t for t in json.loads(volcados[0].read_text())
                         if t['id'] == ident)
            assert tarea['estado'] == 'cancelada'
        finally:
            if proceso.poll() is None:
                proceso.kill()
                proceso.wait(timeout=3)
