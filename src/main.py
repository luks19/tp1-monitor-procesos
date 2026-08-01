"""main.py — Entry point del monitor de procesos."""
import os
import sys
import signal
import time
import json
import argparse
import multiprocessing
from multiprocessing import Process, Manager, Event, Value

from src.agregador import crear_snapshot
from src.analizadores import (resumen, memoria, fds,
                               threads, senales, scheduling, sistema)
from src.utils import dump_snapshot

INTERVALOS_DEFAULT = {
    'resumen':    2.0,
    'memoria':    3.0,
    'fds':        5.0,
    'threads':    2.0,
    'senales':   10.0,
    'scheduling':10.0,
    'sistema':    2.0,
}


def cargar_config(ruta='config.json'):
    try:
        with open(ruta) as f:
            cfg = json.load(f)
        return cfg.get('intervalos', INTERVALOS_DEFAULT)
    except (FileNotFoundError, json.JSONDecodeError):
        return INTERVALOS_DEFAULT


def lanzar_analizadores(snapshot, pids, stop_event, intervalos):
    config = [
        (resumen,    'resumen',    intervalos['resumen']),
        (memoria,    'memoria',    intervalos['memoria']),
        (fds,        'fds',        intervalos['fds']),
        (threads,    'threads',    intervalos['threads']),
        (senales,    'senales',    intervalos['senales']),
        (scheduling, 'scheduling', intervalos['scheduling']),
        (sistema,    'sistema',    intervalos['sistema']),
    ]
    procesos = []
    for modulo, nombre, intervalo in config:
        p = Process(
            target=modulo.analizar,
            args=(snapshot, pids, intervalo, stop_event),
            name=f'analizador-{nombre}',
            daemon=True,
        )
        p.start()
        procesos.append(p)
    return procesos


def main():
    parser = argparse.ArgumentParser(description='Monitor de procesos - Computacion 2')
    parser.add_argument('--config', default='config.json')
    args = parser.parse_args()

    intervalos = cargar_config(args.config)

    manager  = Manager()
    snapshot = crear_snapshot(manager)
    stop_event  = Event()
    flag_dump    = Value('b', 0)
    flag_verbose = Value('b', 0)
    flag_reload  = Value('b', 0)

    def handler_shutdown(sig, frame):
        stop_event.set()

    def handler_dump(sig, frame):
        flag_dump.value = 1

    def handler_verbose(sig, frame):
        flag_verbose.value = 1 - flag_verbose.value

    def handler_reload(sig, frame):
        flag_reload.value = 1

    signal.signal(signal.SIGINT,  handler_shutdown)
    signal.signal(signal.SIGTERM, handler_shutdown)
    signal.signal(signal.SIGUSR1, handler_dump)
    signal.signal(signal.SIGUSR2, handler_verbose)
    signal.signal(signal.SIGHUP,  handler_reload)

    # Lista inicial de PIDs
    from src import procfs
    pids_iniciales = procfs.listar_pids()

    print(f'[Monitor] PID={os.getpid()} — iniciando {len(pids_iniciales)} procesos encontrados...')
    analizadores = lanzar_analizadores(snapshot, pids_iniciales, stop_event, intervalos)
    print(f'[Monitor] {len(analizadores)} analizadores corriendo. Esperando primera lectura...')
    time.sleep(2)

    from src.display import iniciar_tui
    iniciar_tui(snapshot, stop_event, flag_dump, flag_verbose,
                flag_reload, intervalos, args.config)

    print('\n[Monitor] Deteniendo...')
    stop_event.set()
    for p in analizadores:
        p.join(timeout=3)
    manager.shutdown()
    print('[Monitor] Salida limpia.')


if __name__ == '__main__':
    main()
