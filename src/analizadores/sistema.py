"""Analizador de stats globales del sistema."""
import time
from src import procfs


def analizar(snapshot, pids, intervalo, stop_event):
    jiffies_prev = None
    ts_prev = None

    while not stop_event.is_set():
        ahora = time.time()
        datos = procfs.leer_sistema()

        # Calcular CPU% global usando delta de jiffies
        if jiffies_prev is not None and ts_prev is not None:
            elapsed = ahora - ts_prev
            j = datos['cpu_jiffies']
            jp = jiffies_prev
            total_delta = sum(j.values()) - sum(jp.values())
            idle_delta = j['idle'] - jp['idle']
            if total_delta > 0:
                datos['cpu_pct'] = round((1 - idle_delta / total_delta) * 100, 1)
            else:
                datos['cpu_pct'] = 0.0
        else:
            datos['cpu_pct'] = 0.0

        jiffies_prev = datos['cpu_jiffies'].copy()
        ts_prev = ahora

        snapshot['sistema']['datos'] = datos
        snapshot['sistema']['ts'] = ahora
        stop_event.wait(timeout=intervalo)
