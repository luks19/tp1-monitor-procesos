import os
import time
import procfs

# Frecuencia de ticks del kernel obtenida dinámicamente
CLK_TCK = float(os.sysconf(os.sysconf_names['SC_CLK_TCK']))

def ejecutar_analizador_resumen(snapshot_dict, intervalo_val, stop_event):
    """
    Analizador del resumen del sistema y procesos.
    Relista dinámicamente los PIDs en cada iteración y utiliza el SC_CLK_TCK del sistema.
    """
    tiempos_previos = {}
    timestamp_previo = time.time()

    while not stop_event.is_set():
        pids_actuales = procfs.listar_pids()
        timestamp_actual = time.time()
        delta_tiempo = max(0.0001, timestamp_actual - timestamp_previo)
        
        lista_resumen = []
        nuevos_tiempos = {}

        for pid in pids_actuales:
            stat = procfs.leer_stat(pid)
            if not stat:
                continue
            
            status = procfs.leer_status(pid)
            cmdline = procfs.leer_cmdline(pid)
            
            # Cálculo de %CPU
            tiempo_total_proc = stat['utime'] + stat['stime']
            nuevos_tiempos[pid] = tiempo_total_proc
            
            tiempo_ant = tiempos_previos.get(pid, tiempo_total_proc)
            delta_proc_ticks = max(0, tiempo_total_proc - tiempo_ant)
            
            # cpu_pct = (ticks_consumidos / CLK_TCK) / tiempo_transcurrido * 100
            cpu_pct = round(((delta_proc_ticks / CLK_TCK) / delta_tiempo) * 100.0, 1)

            nombre_cmd = cmdline if cmdline else stat['comm']
            usuario = status['usuario'] if status else 'unknown'
            uid = status['uid'] if status else -1
            gid = status['gid'] if status else -1
            vm_rss = status['vm_rss'] if status else '0 kB'

            lista_resumen.append({
                'pid': pid,
                'usuario': usuario,
                'uid': uid,
                'gid': gid,
                'priority': stat['priority'],
                'nice': stat['nice'],
                'vm_rss': vm_rss,
                'state': stat['state'],
                'cpu_pct': cpu_pct,
                'command': nombre_cmd,
                'minflt': stat['minflt'],
                'majflt': stat['majflt'],
                'policy': stat['policy'],
                'rt_priority': stat['rt_priority']
            })

        # Ordenar por uso de CPU descendente por defecto
        lista_resumen.sort(key=lambda x: x['cpu_pct'], reverse=True)

        snapshot_dict['resumen'] = {
            'timestamp': timestamp_actual,
            'procesos': lista_resumen,
            'total_procesos': len(lista_resumen)
        }

        tiempos_previos = nuevos_tiempos
        timestamp_previo = timestamp_actual

        # Espera dinámica basada en el objeto de memoria compartida
        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break
