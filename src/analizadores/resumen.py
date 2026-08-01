"""Analizador de resumen: PID, estado, CPU%, RSS, threads, comando."""
import time
from src import procfs


def analizar(snapshot, pids, intervalo, stop_event):
    tiempos_prev = {}

    while not stop_event.is_set():
        ahora = time.time()
        datos = {}

        for pid in pids:
            try:
                info = procfs.leer_proceso(pid)
                clave = str(pid)

                if clave in tiempos_prev:
                    t_prev, ts_prev = tiempos_prev[clave]
                    elapsed = ahora - ts_prev
                    if elapsed > 0:
                        delta = (info['utime'] + info['stime']) - t_prev
                        cpu_pct = round((delta / 100.0) / elapsed * 100, 1)
                    else:
                        cpu_pct = 0.0
                else:
                    cpu_pct = 0.0

                tiempos_prev[clave] = (info['utime'] + info['stime'], ahora)

                datos[pid] = {
                    'pid': pid,
                    'ppid': info['ppid'],
                    'estado': info['estado'],
                    'nombre': info['nombre'],
                    'cmdline': info['cmdline'],
                    'threads': info['threads'],
                    'vmrss_kb': info['vmrss_kb'],
                    'cpu_pct': cpu_pct,
                    'nice': info['nice'],
                    'priority': info['priority'],
                }
            except (FileNotFoundError, ProcessLookupError):
                continue

        snapshot['resumen']['datos'] = datos
        snapshot['resumen']['ts'] = ahora
        stop_event.wait(timeout=intervalo)
