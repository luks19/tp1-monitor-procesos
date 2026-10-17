import time
import procfs

def ejecutar_analizador_scheduling(snapshot_dict, intervalo_val, stop_event):
    while not stop_event.is_set():
        pids = procfs.listar_pids()
        datos_sched = []

        for pid in pids:
            stat = procfs.leer_stat(pid)
            if not stat:
                continue

            status = procfs.leer_status(pid)
            cmdline = procfs.leer_cmdline(pid)
            nombre = cmdline if cmdline else stat['comm']
            cpus_allowed = status['cpus_allowed_list'] if status else ''

            datos_sched.append({
                'pid': pid,
                'nombre': nombre,
                'usuario': status['usuario'] if status else 'unknown',
                'policy': stat['policy'],
                'priority': stat['priority'],
                'rt_priority': stat['rt_priority'],
                'nice': stat['nice'],
                'cpus_allowed': cpus_allowed,
                'ppid': stat['ppid'], 'pgrp': stat['pgrp'], 'session': stat['session'],
                'utime': stat['utime'], 'stime': stat['stime'],
                'voluntary_ctxt_switches': status['voluntary_ctxt_switches'] if status else 0,
                'nonvoluntary_ctxt_switches': status['nonvoluntary_ctxt_switches'] if status else 0
            })

        snapshot_dict['scheduling'] = {
            'timestamp': time.time(),
            'procesos': datos_sched,
            'total_procesos': len(datos_sched)
        }

        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break
