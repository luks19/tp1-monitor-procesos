import time
import procfs

def ejecutar_analizador_fds(snapshot_dict, intervalo_val, stop_event):
    while not stop_event.is_set():
        pids = procfs.listar_pids()
        datos_fds = []

        for pid in pids:
            fds = procfs.leer_fds(pid)
            stat = procfs.leer_stat(pid)
            cmdline = procfs.leer_cmdline(pid)

            nombre = cmdline if cmdline else (stat['comm'] if stat else f'PID {pid}')

            datos_fds.append({
                'pid': pid,
                'nombre': nombre,
                'cantidad_fds': len(fds),
                'fds': fds
            })

        datos_fds.sort(key=lambda x: x['cantidad_fds'], reverse=True)

        snapshot_dict['fds'] = {
            'timestamp': time.time(),
            'procesos': datos_fds,
            'total_procesos': len(datos_fds)
        }

        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break