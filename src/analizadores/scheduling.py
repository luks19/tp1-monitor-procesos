"""Analizador de scheduling."""
import time
from src import procfs


def analizar(snapshot, pids, intervalo, stop_event):
    while not stop_event.is_set():
        datos = {}
        for pid in pids:
            try:
                stat = procfs.leer_stat(pid)
                ctx_vol, ctx_invol = procfs.leer_context_switches(
                    f'/proc/{pid}/status')
                datos[pid] = {
                    'nice':            stat['nice'],
                    'priority':        stat['priority'],
                    'pgid':            stat['pgid'],
                    'sid':             stat['sid'],
                    'ctx_voluntarios': ctx_vol,
                    'ctx_involuntarios': ctx_invol,
                }
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        snapshot['scheduling']['datos'] = datos
        snapshot['scheduling']['ts'] = time.time()
        stop_event.wait(timeout=intervalo)
