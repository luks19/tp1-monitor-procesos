import time
import procfs

def ejecutar_analizador_sistema(snapshot_dict, intervalo_val, stop_event):
    while not stop_event.is_set():
        pids = procfs.listar_pids()
        conteo_estados = {}

        for pid in pids:
            stat = procfs.leer_stat(pid)
            if stat:
                estado = stat['state']
                conteo_estados[estado] = conteo_estados.get(estado, 0) + 1

        # Uptime y memoria general del sistema
        mem_info = {}
        try:
            with open('/proc/meminfo', 'r') as f:
                for linea in f:
                    k, _, v = linea.partition(':')
                    mem_info[k.strip()] = v.strip()
        except Exception:
            pass

        uptime_seg = 0.0
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seg = float(f.read().split()[0])
        except Exception:
            pass

        snapshot_dict['sistema'] = {
            'timestamp': time.time(),
            'total_procesos': len(pids),
            'estados': conteo_estados,
            'mem_total': mem_info.get('MemTotal', '0 kB'),
            'mem_free': mem_info.get('MemFree', '0 kB'),
            'mem_available': mem_info.get('MemAvailable', '0 kB'),
            'uptime': uptime_seg
        }

        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break