"""Recolector: lista PIDs activos del sistema."""
import time
from src import procfs


def recolectar(intervalo=2.0):
    while True:
        pids = []
        for pid in procfs.listar_pids():
            try:
                procfs.leer_stat(pid)
                pids.append(pid)
            except (FileNotFoundError, ProcessLookupError):
                continue
        yield pids
        time.sleep(intervalo)
