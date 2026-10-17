import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import main


def test_config_carga_filtros_por_defecto_y_admite_reemplazo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main.cargar_filtros() == {'filtro_cmd': '', 'filtro_usr': ''}

    (tmp_path / 'config.json').write_text(json.dumps({
        'resumen': 2,
        'filtro_cmd': 'python',
        'filtro_usr': 'lucas'
    }))
    assert main.cargar_filtros() == {'filtro_cmd': 'python', 'filtro_usr': 'lucas'}


def test_coordinador_procesa_senales_fuera_del_handler(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'config.json').write_text(json.dumps({
        'resumen': 4,
        'filtro_cmd': 'python',
        'filtro_usr': 'lucas'
    }))

    class Valor:
        def __init__(self, value):
            self.value = value

    class Evento:
        detenido = False

        def is_set(self):
            return self.detenido

        def set(self):
            self.detenido = True

    evento = Evento()
    intervalos = {nombre: Valor(2) for nombre in main.CONFIG_DEFAULT}
    flag_verbose = Valor(0)
    cola_filtros = main.queue.Queue()
    cola_senales = main.queue.SimpleQueue()
    for senal in (signal.SIGHUP, signal.SIGUSR2, signal.SIGUSR1, signal.SIGTERM):
        cola_senales.put(senal)

    main.loop_senales(evento, flag_verbose, {}, intervalos, cola_filtros, cola_senales)

    assert intervalos['resumen'].value == 4
    assert cola_filtros.get_nowait() == {'filtro_cmd': 'python', 'filtro_usr': 'lucas'}
    assert flag_verbose.value == 1
    assert evento.is_set()
    assert list(tmp_path.glob('dump_*.json'))
