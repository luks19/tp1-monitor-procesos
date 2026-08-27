import os
import sys
import json
import time
import signal
import threading
import multiprocessing
from multiprocessing import Process, Manager, Value, Event

import display
from analizadores.resumen import ejecutar_analizador_resumen
from analizadores.memoria import ejecutar_analizador_memoria
from analizadores.fds import ejecutar_analizador_fds
from analizadores.senales import ejecutar_analizador_senales
from analizadores.threads import ejecutar_analizador_threads
from analizadores.scheduling import ejecutar_analizador_scheduling
from analizadores.sistema import ejecutar_analizador_sistema

CONFIG_DEFAULT = {
    'resumen': 1.0,
    'memoria': 2.0,
    'fds': 3.0,
    'senales': 5.0,
    'threads': 2.0,
    'scheduling': 5.0,
    'sistema': 2.0
}

INTERVALOS_MINIMOS = {
    'resumen': 0.5,
    'threads': 0.5,
    'memoria': 1.0,
    'sistema': 1.0,
    'fds': 2.0,
    'senales': 5.0,
    'scheduling': 5.0
}

def cargar_config():
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r') as f:
                cfg = json.load(f)
                return {k: max(INTERVALOS_MINIMOS.get(k, 0.5), float(cfg.get(k, v))) for k, v in CONFIG_DEFAULT.items()}
        except Exception:
            pass
    return CONFIG_DEFAULT.copy()

def loop_senales(stop_event, flag_dump, flag_verbose, flag_reload, snapshot_dict, intervalos_sync):
    while not stop_event.is_set():
        if flag_reload.value == 1:
            cfg = cargar_config()
            for k, val in cfg.items():
                if k in intervalos_sync:
                    intervalos_sync[k].value = val
            flag_reload.value = 0

        if flag_dump.value == 1:
            try:
                nombre_dump = f"dump_{int(time.time())}.json"
                with open(nombre_dump, 'w') as f:
                    json.dump(dict(snapshot_dict), f, indent=2)
            except Exception:
                pass
            flag_dump.value = 0

        time.sleep(0.2)

def main():
    config = cargar_config()

    flag_dump = Value('b', 0)
    flag_verbose = Value('b', 0)
    flag_reload = Value('b', 0)
    stop_event = Event()

    intervalos_sync = {
        k: Value('d', config[k]) for k in CONFIG_DEFAULT.keys()
    }

    def handler_sighup(signum, frame):
        flag_reload.value = 1

    def handler_sigusr1(signum, frame):
        flag_dump.value = 1

    def handler_sigusr2(signum, frame):
        flag_verbose.value = 0 if flag_verbose.value == 1 else 1

    def handler_sigterm(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGHUP, handler_sighup)
    signal.signal(signal.SIGUSR1, handler_sigusr1)
    signal.signal(signal.SIGUSR2, handler_sigusr2)
    signal.signal(signal.SIGINT, handler_sigterm)
    signal.signal(signal.SIGTERM, handler_sigterm)

    manager = Manager()
    snapshot_dict = manager.dict()

    workers_map = {
        'resumen': ejecutar_analizador_resumen,
        'memoria': ejecutar_analizador_memoria,
        'fds': ejecutar_analizador_fds,
        'senales': ejecutar_analizador_senales,
        'threads': ejecutar_analizador_threads,
        'scheduling': ejecutar_analizador_scheduling,
        'sistema': ejecutar_analizador_sistema
    }

    procesos = []
    for nombre, fn in workers_map.items():
        p = Process(
            target=fn,
            args=(snapshot_dict, intervalos_sync[nombre], stop_event),
            name=f'analizador-{nombre}'
        )
        p.start()
        procesos.append(p)

    hilo_sig = threading.Thread(
        target=loop_senales,
        args=(stop_event, flag_dump, flag_verbose, flag_reload, snapshot_dict, intervalos_sync),
        daemon=True
    )
    hilo_sig.start()

    try:
        display.iniciar_tui(snapshot_dict, intervalos_sync, flag_verbose, stop_event)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        for p in procesos:
            p.join(timeout=1.5)
            if p.is_alive():
                p.terminate()
        manager.shutdown()

if __name__ == '__main__':
    main()