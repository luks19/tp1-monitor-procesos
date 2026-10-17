import os
import sys
import json
import time
import signal
import threading
import multiprocessing
import queue
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
    'resumen': 2.0,
    'memoria': 3.0,
    'fds': 5.0,
    'senales': 10.0,
    'threads': 2.0,
    'scheduling': 10.0,
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

def cargar_filtros():
    defaults = {'filtro_cmd': '', 'filtro_usr': ''}
    try:
        with open('config.json', 'r') as archivo:
            cfg = json.load(archivo)
        return {clave: str(cfg.get(clave, valor)) for clave, valor in defaults.items()}
    except (OSError, ValueError, TypeError):
        return defaults

def loop_senales(stop_event, flag_verbose, snapshot_dict, intervalos_sync, cola_filtros, cola_senales):
    while not stop_event.is_set():
        try:
            senal = cola_senales.get_nowait()
        except queue.Empty:
            stop_event.wait(timeout=0.2)
            continue

        if senal == signal.SIGHUP:
            cfg = cargar_config()
            for k, val in cfg.items():
                if k in intervalos_sync:
                    intervalos_sync[k].value = val
            cola_filtros.put(cargar_filtros())
        elif senal == signal.SIGUSR1:
            try:
                nombre_dump = f"dump_{int(time.time())}.json"
                with open(nombre_dump, 'w') as f:
                    json.dump(dict(snapshot_dict), f, indent=2)
            except OSError:
                pass
        elif senal == signal.SIGUSR2:
            flag_verbose.value = 0 if flag_verbose.value else 1
        elif senal in (signal.SIGINT, signal.SIGTERM):
            stop_event.set()

def main():
    config = cargar_config()

    flag_verbose = Value('b', 0)
    cola_senales = queue.SimpleQueue()
    stop_event = Event()

    intervalos_sync = {
        k: Value('d', config[k]) for k in CONFIG_DEFAULT.keys()
    }

    def encolar_senal(signum, frame):
        cola_senales.put(signum)

    for senal in (signal.SIGHUP, signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT, signal.SIGTERM):
        signal.signal(senal, encolar_senal)

    manager = Manager()
    snapshot_dict = manager.dict()
    cola_filtros = queue.Queue()

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
        args=(stop_event, flag_verbose, snapshot_dict, intervalos_sync, cola_filtros, cola_senales),
        daemon=True
    )
    hilo_sig.start()

    try:
        display.iniciar_tui(snapshot_dict, intervalos_sync, flag_verbose, stop_event, cargar_filtros(), cola_filtros)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        hilo_sig.join()
        for p in procesos:
            p.join(timeout=1.5)
            if p.is_alive():
                p.terminate()
                p.join()
        manager.shutdown()

if __name__ == '__main__':
    main()
