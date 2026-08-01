"""Analizador de threads (LWPs)."""
import time
from src import procfs


def analizar(snapshot, pids, intervalo, stop_event):
    while not stop_event.is_set():
        datos = {}
        for pid in pids:
            try:
                datos[pid] = procfs.listar_threads(pid)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        snapshot['threads']['datos'] = datos
        snapshot['threads']['ts'] = time.time()
        stop_event.wait(timeout=intervalo)
