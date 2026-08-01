"""Analizador de memoria: segmentos, swap."""
import time
from src import procfs


def analizar(snapshot, pids, intervalo, stop_event):
    while not stop_event.is_set():
        datos = {}
        for pid in pids:
            try:
                status = procfs.leer_status(pid)
                try:
                    maps = procfs.leer_maps(pid)
                except PermissionError:
                    maps = {}
                datos[pid] = {
                    'vmsize_kb': status['vmsize_kb'],
                    'vmrss_kb':  status['vmrss_kb'],
                    'vmdata_kb': status['vmdata_kb'],
                    'vmstk_kb':  status['vmstk_kb'],
                    'vmexe_kb':  status['vmexe_kb'],
                    'vmlib_kb':  status['vmlib_kb'],
                    'vmswap_kb': status['vmswap_kb'],
                    'segmentos': maps,
                }
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        snapshot['memoria']['datos'] = datos
        snapshot['memoria']['ts'] = time.time()
        stop_event.wait(timeout=intervalo)
