import os
import time
import procfs

def ejecutar_analizador_threads(snapshot_dict, intervalo_val, stop_event):
    tiempos_previos = {}
    anterior = time.time()
    while not stop_event.is_set():
        pids = procfs.listar_pids()
        datos_threads = []
        ahora = time.time()
        delta_tiempo = max(0.0001, ahora - anterior)
        clk_tck = float(os.sysconf('SC_CLK_TCK'))
        tiempos_nuevos = {}

        for pid in pids:
            stat = procfs.leer_stat(pid)
            if not stat:
                continue

            status = procfs.leer_status(pid)
            
            cmdline = procfs.leer_cmdline(pid)
            nombre = cmdline if cmdline else stat['comm']

            threads = []
            for thread in procfs.leer_threads(pid):
                clave = (pid, thread['tid'])
                ticks = thread['utime'] + thread['stime']
                ticks_previos = tiempos_previos.get(clave, ticks)
                threads.append({
                    **thread,
                    'cpu_pct': round(max(0, ticks - ticks_previos) / clk_tck / delta_tiempo * 100, 1)
                })
                tiempos_nuevos[clave] = ticks

            datos_threads.append({
                'pid': pid,
                'nombre': nombre,
                'usuario': status['usuario'] if status else 'unknown',
                'num_threads': stat['num_threads'],
                'state': stat['state'],
                'priority': stat['priority'],
                'nice': stat['nice'],
                'threads': threads
            })

        datos_threads.sort(key=lambda x: x['num_threads'], reverse=True)

        snapshot_dict['threads'] = {
            'timestamp': time.time(),
            'procesos': datos_threads,
            'total_procesos': len(datos_threads)
        }

        tiempos_previos = tiempos_nuevos
        anterior = ahora

        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break
