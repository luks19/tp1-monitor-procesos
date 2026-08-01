"""Analizador de señales."""
import time
from src import procfs


def analizar(snapshot, pids, intervalo, stop_event):
    while not stop_event.is_set():
        datos = {}
        for pid in pids:
            try:
                datos[pid] = procfs.leer_senales(pid)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        snapshot['senales']['datos'] = datos
        snapshot['senales']['ts'] = time.time()
        stop_event.wait(timeout=intervalo)
