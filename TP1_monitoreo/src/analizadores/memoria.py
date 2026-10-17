import time
import procfs

def ejecutar_analizador_memoria(snapshot_dict, intervalo_val, stop_event):
    while not stop_event.is_set():
        pids = procfs.listar_pids()
        datos_memoria = []

        for pid in pids:
            maps = procfs.leer_maps(pid)
            if not maps:
                continue
            
            status = procfs.leer_status(pid)
            stat = procfs.leer_stat(pid)
            cmdline = procfs.leer_cmdline(pid)

            nombre = cmdline if cmdline else (stat['comm'] if stat else f'PID {pid}')
            
            datos_memoria.append({
                'pid': pid,
                'nombre': nombre,
                'vm_size': status['vm_size'] if status else '0 kB',
                'vm_rss': status['vm_rss'] if status else '0 kB',
                'vm_hwm': status['vm_hwm'] if status else '0 kB',
                'minflt': stat['minflt'] if stat else 0,
                'majflt': stat['majflt'] if stat else 0,
                'heap_kb': maps['heap_kb'],
                'stack_kb': maps['stack_kb'],
                'so_kb': maps['so_kb'],
                'bin_kb': maps['bin_kb'],
                'total_kb': maps['total_kb']
            })

        datos_memoria.sort(key=lambda x: x['total_kb'], reverse=True)

        snapshot_dict['memoria'] = {
            'timestamp': time.time(),
            'procesos': datos_memoria,
            'total_procesos': len(datos_memoria)
        }

        t_espera = intervalo_val.value
        if stop_event.wait(timeout=t_espera):
            break