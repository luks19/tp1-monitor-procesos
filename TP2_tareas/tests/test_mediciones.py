import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('modo', ['io', 'cpu', 'pool'])
def test_medicion_reproducible_con_servicio_real(tmp_path, modo):
    destino = tmp_path / f'{modo}.json'
    r = subprocess.run([
        sys.executable, '-m', 'TP2_tareas.mediciones', modo,
        '--salida', str(destino), '--iteraciones', '400000',
        '--cantidades', '2', '4', '8', '--demora', '0.03',
        '--workers', '2', '--procesos', '1',
    ], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
        timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    datos = json.loads(destino.read_text())
    assert datos['modo'] == modo
    assert datos['entorno']['python']
    if modo == 'io':
        assert datos['descargas'] == 20
        assert datos['exitosas_secuenciales'] == datos['exitosas_concurrentes'] == 20
        assert datos['speedup'] > 2
    elif modo == 'cpu':
        assert datos['sin_executor']['estado'] == 'completada'
        assert datos['con_executor']['estado'] == 'completada'
        assert datos['sin_executor']['get_segundos'] > datos['con_executor']['get_segundos']
    else:
        assert [f['cantidad'] for f in datos['lotes']] == [2, 4, 8]
        assert all(f['completadas'] == f['cantidad'] for f in datos['lotes'])
        assert all(f['latencia_p95'] <= f['total_segundos'] for f in datos['lotes'])
        assert datos['lotes'][-1]['espera_cola_promedio'] > datos['lotes'][0]['espera_cola_promedio']
