import time
import procfs

def ejecutar_analizador_threads(snapshot_dict, intervalo_val, stop_event):
    while not stop_event.is_set():
        pids = procfs.listar_pids()
        datos_threads = []

        for pid in pids:
            stat = procfs.leer_stat(pid)
            if not stat:
                continue

            status = procfs.leer_status(pid)
            
            cmdline = procfs.leer_cmdline(pid)
            nombre = cmdline if cmdline else stat['comm']

            datos_threads.append({
                'pid': pid,
                'nombre': nombre,
                'usuario': status['usuario'] if status else 'unknown',
                'num_threads': stat['num_threads'],
                'state': stat['state'],
                'priority': stat['priority'],
                'nice': stat['nice']
            })

        datos_threads.sort(key=lambda x: x['num_threads'], reverse=True)

        snapshot_dict['threads'] = {
            'timestamp': time.time(),
            'procesos': datos_threads,
            'total_procesos': len(datos_threads)
        }

        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break
