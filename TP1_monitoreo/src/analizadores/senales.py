import time
import procfs

def ejecutar_analizador_senales(snapshot_dict, intervalo_val, stop_event):
    while not stop_event.is_set():
        pids = procfs.listar_pids()
        datos_senales = []

        for pid in pids:
            status = procfs.leer_status(pid)
            if not status:
                continue

            stat = procfs.leer_stat(pid)
            cmdline = procfs.leer_cmdline(pid)
            nombre = cmdline if cmdline else (stat['comm'] if stat else f'PID {pid}')

            datos_senales.append({
                'pid': pid,
                'nombre': nombre,
                'usuario': status['usuario'],
                'bloqueadas': procfs.decodificar_senales(status['sig_blk']),
                'ignoradas': procfs.decodificar_senales(status['sig_ign']),
                'con_handler': procfs.decodificar_senales(status['sig_cgt']),
                'pendientes': procfs.decodificar_senales(status['sig_pnd']),
                'pendientes_compartidas': procfs.decodificar_senales(status['shd_pnd'])
            })

        snapshot_dict['senales'] = {
            'timestamp': time.time(),
            'procesos': datos_senales,
            'total_procesos': len(datos_senales)
        }

        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break
