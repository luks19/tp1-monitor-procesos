"""Analizador de file descriptors."""
import time
from src import procfs


def analizar(snapshot, pids, intervalo, stop_event):
    while not stop_event.is_set():
        datos = {}
        for pid in pids:
            try:
                datos[pid] = procfs.listar_fds(pid)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        snapshot['fds']['datos'] = datos
        snapshot['fds']['ts'] = time.time()
        stop_event.wait(timeout=intervalo)
