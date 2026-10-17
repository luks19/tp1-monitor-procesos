import os
import time
import procfs


def _leer_cpu():
    try:
        with open('/proc/stat', 'r') as archivo:
            campos = archivo.readline().split()[1:]
            return [int(valor) for valor in campos]
    except (OSError, ValueError):
        return []


def ejecutar_analizador_sistema(snapshot_dict, intervalo_val, stop_event):
    cpu_previo = _leer_cpu()
    cpu_procesos_previo = {}
    instante_previo = time.time()
    while not stop_event.is_set():
        instante = time.time()
        delta_tiempo = max(0.0001, instante - instante_previo)
        pids = procfs.listar_pids()
        conteo_estados = {}
        total_threads = 0
        procesos = []
        cpu_procesos = {}
        for pid in pids:
            stat = procfs.leer_stat(pid)
            if not stat:
                continue
            conteo_estados[stat['state']] = conteo_estados.get(stat['state'], 0) + 1
            status = procfs.leer_status(pid)
            total_threads += status['threads'] if status else stat['num_threads']
            procesos.append((pid, stat['comm'], stat['utime'] + stat['stime'], status['vm_rss'] if status else '0 kB'))
            cpu_procesos[pid] = stat['utime'] + stat['stime']

        mem_info = {}
        try:
            with open('/proc/meminfo', 'r') as f:
                for linea in f:
                    k, _, v = linea.partition(':')
                    mem_info[k.strip()] = v.strip()
        except OSError:
            pass
        uptime_seg = 0.0
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seg = float(f.read().split()[0])
        except (OSError, ValueError, IndexError):
            pass
        loadavg = '-'
        try:
            with open('/proc/loadavg', 'r') as f:
                loadavg = ' '.join(f.read().split()[:3])
        except OSError:
            pass
        btime = 0
        try:
            with open('/proc/stat', 'r') as f:
                btime = int(next(line.split()[1] for line in f if line.startswith('btime ')))
        except (OSError, ValueError, StopIteration):
            pass

        cpu_actual = _leer_cpu()
        cpu_pct = {}
        if cpu_previo and cpu_actual and len(cpu_previo) == len(cpu_actual):
            delta = [max(0, a - b) for a, b in zip(cpu_actual, cpu_previo)]
            total = sum(delta) or 1
            cpu_pct = {
                'user': round(delta[0] * 100 / total, 1),
                'system': round((delta[2] + delta[5] + delta[6]) * 100 / total, 1),
                'idle': round(delta[3] * 100 / total, 1),
                'iowait': round(delta[4] * 100 / total, 1)
            }
        cpu_previo = cpu_actual
        ticks = float(os.sysconf('SC_CLK_TCK'))
        top_cpu = sorted(
            procesos,
            key=lambda p: max(0, p[2] - cpu_procesos_previo.get(p[0], p[2])) / ticks / delta_tiempo,
            reverse=True
        )[:3]
        top_mem = sorted(procesos, key=lambda p: int(p[3].split()[0]) if p[3].split() else 0, reverse=True)[:3]
        snapshot_dict['sistema'] = {
            'timestamp': time.time(), 'total_procesos': len(procesos), 'estados': conteo_estados,
            'total_threads': total_threads, 'zombies': conteo_estados.get('Z', 0),
            'mem_total': mem_info.get('MemTotal', '0 kB'), 'mem_free': mem_info.get('MemFree', '0 kB'),
            'mem_available': mem_info.get('MemAvailable', '0 kB'), 'buffers': mem_info.get('Buffers', '0 kB'),
            'cached': mem_info.get('Cached', '0 kB'), 'swap_total': mem_info.get('SwapTotal', '0 kB'),
            'swap_free': mem_info.get('SwapFree', '0 kB'), 'uptime': uptime_seg, 'btime': btime,
            'loadavg': loadavg, 'cpu_pct': cpu_pct,
            'top_cpu': [{'pid': p[0], 'nombre': p[1], 'cpu_pct': round(max(0, p[2] - cpu_procesos_previo.get(p[0], p[2])) / ticks / delta_tiempo * 100, 1)} for p in top_cpu],
            'top_mem': [{'pid': p[0], 'nombre': p[1], 'rss': p[3]} for p in top_mem]
        }
        cpu_procesos_previo = cpu_procesos
        instante_previo = instante
        if stop_event.wait(timeout=intervalo_val.value):
            break
