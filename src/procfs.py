"""
procfs.py — Funciones para leer datos de procesos desde /proc.
"""
import os


NOMBRES_SENALES = {
    1: 'SIGHUP', 2: 'SIGINT', 3: 'SIGQUIT', 4: 'SIGILL',
    5: 'SIGTRAP', 6: 'SIGABRT', 7: 'SIGBUS', 8: 'SIGFPE',
    9: 'SIGKILL', 10: 'SIGUSR1', 11: 'SIGSEGV', 12: 'SIGUSR2',
    13: 'SIGPIPE', 14: 'SIGALRM', 15: 'SIGTERM', 16: 'SIGSTKFLT',
    17: 'SIGCHLD', 18: 'SIGCONT', 19: 'SIGSTOP', 20: 'SIGTSTP',
    21: 'SIGTTIN', 22: 'SIGTTOU', 23: 'SIGURG', 24: 'SIGXCPU',
    25: 'SIGXFSZ', 26: 'SIGVTALRM', 27: 'SIGPROF', 28: 'SIGWINCH',
    29: 'SIGIO', 30: 'SIGPWR', 31: 'SIGSYS',
}


def listar_pids():
    pids = []
    for entrada in os.listdir('/proc'):
        if entrada.isdigit():
            pids.append(int(entrada))
    return pids


def leer_stat(pid):
    with open(f'/proc/{pid}/stat', 'r') as f:
        linea = f.read()
    inicio_nombre = linea.find('(')
    fin_nombre = linea.rfind(')')
    pid_str = linea[:inicio_nombre].strip()
    nombre = linea[inicio_nombre+1:fin_nombre]
    resto = linea[fin_nombre+2:].split()
    return {
        'pid': int(pid_str),
        'nombre': nombre,
        'estado': resto[0],
        'ppid': int(resto[1]),
        'pgid': int(resto[3]),
        'sid': int(resto[4]),
        'utime': int(resto[11]),
        'stime': int(resto[12]),
        'priority': int(resto[15]),
        'nice': int(resto[16]),
    }


def leer_stat_en_ruta(ruta):
    with open(ruta, 'r') as f:
        linea = f.read()
    inicio_nombre = linea.find('(')
    fin_nombre = linea.rfind(')')
    resto = linea[fin_nombre+2:].split()
    return {
        'estado': resto[0],
        'utime': int(resto[11]),
        'stime': int(resto[12]),
    }


def leer_status(pid):
    datos = {}
    with open(f'/proc/{pid}/status', 'r') as f:
        for linea in f:
            clave, _, valor = linea.partition(':')
            datos[clave.strip()] = valor.strip()
    return {
        'nombre': datos.get('Name', ''),
        'estado_raw': datos.get('State', ''),
        'ppid': int(datos.get('PPid', 0)),
        'threads': int(datos.get('Threads', 1)),
        'vmsize_kb': datos.get('VmSize', '0 kB'),
        'vmrss_kb': datos.get('VmRSS', '0 kB'),
        'vmdata_kb': datos.get('VmData', '0 kB'),
        'vmstk_kb': datos.get('VmStk', '0 kB'),
        'vmexe_kb': datos.get('VmExe', '0 kB'),
        'vmlib_kb': datos.get('VmLib', '0 kB'),
        'vmswap_kb': datos.get('VmSwap', '0 kB'),
        'sigblk': datos.get('SigBlk', '0'),
        'sigign': datos.get('SigIgn', '0'),
        'sigcgt': datos.get('SigCgt', '0'),
        'sigpnd': datos.get('SigPnd', '0'),
        'shdpnd': datos.get('ShdPnd', '0'),
    }


def leer_cmdline(pid):
    with open(f'/proc/{pid}/cmdline', 'rb') as f:
        contenido = f.read()
    partes = contenido.split(b'\x00')
    partes = [p.decode('utf-8', errors='replace') for p in partes if p]
    return ' '.join(partes)


def leer_maps(pid):
    grupos = {'text': 0, 'heap': 0, 'stack': 0, 'data': 0,
              'anonima': 0, 'shared': 0, 'otros': 0}
    with open(f'/proc/{pid}/maps', 'r') as f:
        for linea in f:
            partes = linea.split(None, 5)
            rango = partes[0]
            permisos = partes[1]
            path = partes[5].strip() if len(partes) > 5 else ''
            inicio_str, fin_str = rango.split('-')
            tamaño_kb = (int(fin_str, 16) - int(inicio_str, 16)) // 1024
            if '[heap]' in path:
                grupos['heap'] += tamaño_kb
            elif '[stack]' in path:
                grupos['stack'] += tamaño_kb
            elif 'x' in permisos and path.startswith('/'):
                grupos['text'] += tamaño_kb
            elif path.endswith('.so') or '.so.' in path:
                grupos['shared'] += tamaño_kb
            elif path == '' and 'w' in permisos:
                grupos['anonima'] += tamaño_kb
            elif path.startswith('/') and 'w' in permisos:
                grupos['data'] += tamaño_kb
            else:
                grupos['otros'] += tamaño_kb
    return grupos


def leer_context_switches(ruta_status):
    vol, invol = 0, 0
    with open(ruta_status, 'r') as f:
        for linea in f:
            if linea.startswith('voluntary_ctxt_switches'):
                vol = int(linea.split(':')[1].strip())
            elif linea.startswith('nonvoluntary_ctxt_switches'):
                invol = int(linea.split(':')[1].strip())
    return vol, invol


def listar_threads(pid):
    threads = []
    ruta_task = f'/proc/{pid}/task'
    for tid_str in os.listdir(ruta_task):
        tid = int(tid_str)
        try:
            info_stat = leer_stat_en_ruta(f'{ruta_task}/{tid_str}/stat')
            with open(f'{ruta_task}/{tid_str}/comm', 'r') as f:
                nombre_thread = f.read().strip()
            ctx_vol, ctx_invol = leer_context_switches(
                f'{ruta_task}/{tid_str}/status')
            threads.append({
                'tid': tid,
                'nombre': nombre_thread,
                'estado': info_stat['estado'],
                'utime': info_stat['utime'],
                'stime': info_stat['stime'],
                'ctx_voluntarios': ctx_vol,
                'ctx_involuntarios': ctx_invol,
            })
        except (FileNotFoundError, ProcessLookupError):
            continue
    return threads


def decodificar_mascara_senales(mascara_hex):
    valor = int(mascara_hex, 16)
    return [nombre for numero, nombre in NOMBRES_SENALES.items()
            if valor & (1 << (numero - 1))]


def leer_senales(pid):
    status = leer_status(pid)
    return {
        'bloqueadas': decodificar_mascara_senales(status['sigblk']),
        'ignoradas': decodificar_mascara_senales(status['sigign']),
        'con_handler': decodificar_mascara_senales(status['sigcgt']),
        'pendientes_proceso': decodificar_mascara_senales(status['sigpnd']),
        'pendientes_grupo': decodificar_mascara_senales(status['shdpnd']),
    }


def listar_fds(pid):
    fds = []
    ruta_fd = f'/proc/{pid}/fd'
    for fd_str in os.listdir(ruta_fd):
        try:
            destino = os.readlink(f'{ruta_fd}/{fd_str}')
        except (FileNotFoundError, PermissionError):
            continue
        if destino.startswith('socket:'):
            tipo = 'socket'
        elif destino.startswith('pipe:'):
            tipo = 'pipe'
        elif destino.startswith('/dev/pts/') or destino.startswith('/dev/tty'):
            tipo = 'tty'
        elif destino.startswith('anon_inode:'):
            tipo = 'anon_inode'
        elif destino.startswith('/'):
            tipo = 'file'
        else:
            tipo = 'otro'
        fds.append({'fd': int(fd_str), 'destino': destino, 'tipo': tipo})
    return sorted(fds, key=lambda x: x['fd'])


def leer_proceso(pid):
    info = {}
    info.update(leer_stat(pid))
    info.update(leer_status(pid))
    try:
        info['cmdline'] = leer_cmdline(pid)
    except Exception:
        info['cmdline'] = f'[{info["nombre"]}]'
    return info


def leer_sistema():
    resultado = {}

    meminfo = {}
    with open('/proc/meminfo', 'r') as f:
        for linea in f:
            clave, _, valor = linea.partition(':')
            meminfo[clave.strip()] = valor.strip()

    resultado['mem_total_kb']   = int(meminfo.get('MemTotal', '0 kB').split()[0])
    resultado['mem_libre_kb']   = int(meminfo.get('MemFree', '0 kB').split()[0])
    resultado['mem_buffers_kb'] = int(meminfo.get('Buffers', '0 kB').split()[0])
    resultado['mem_cached_kb']  = int(meminfo.get('Cached', '0 kB').split()[0])
    resultado['swap_total_kb']  = int(meminfo.get('SwapTotal', '0 kB').split()[0])
    resultado['swap_libre_kb']  = int(meminfo.get('SwapFree', '0 kB').split()[0])
    resultado['mem_usada_kb'] = (
        resultado['mem_total_kb']
        - resultado['mem_libre_kb']
        - resultado['mem_buffers_kb']
        - resultado['mem_cached_kb']
    )

    with open('/proc/loadavg', 'r') as f:
        partes = f.read().split()
    resultado['load_1min']  = float(partes[0])
    resultado['load_5min']  = float(partes[1])
    resultado['load_15min'] = float(partes[2])
    corriendo, totales = partes[3].split('/')
    resultado['procs_corriendo'] = int(corriendo)
    resultado['procs_totales']   = int(totales)

    with open('/proc/stat', 'r') as f:
        linea_cpu = f.readline()
    campos = linea_cpu.split()
    resultado['cpu_jiffies'] = {
        'user':    int(campos[1]),
        'nice':    int(campos[2]),
        'system':  int(campos[3]),
        'idle':    int(campos[4]),
        'iowait':  int(campos[5]),
        'irq':     int(campos[6]),
        'softirq': int(campos[7]),
    }

    estados = {'R': 0, 'S': 0, 'D': 0, 'T': 0, 'Z': 0, 'otros': 0}
    zombies = []
    for pid in listar_pids():
        try:
            with open(f'/proc/{pid}/stat', 'r') as f:
                linea = f.read()
            fin = linea.rfind(')')
            estado = linea[fin+2]
            if estado in estados:
                estados[estado] += 1
            else:
                estados['otros'] += 1
            if estado == 'Z':
                zombies.append(pid)
        except (FileNotFoundError, ProcessLookupError):
            continue

    resultado['estados_procesos'] = estados
    resultado['zombies'] = zombies
    return resultado


if __name__ == '__main__':
    pids = listar_pids()
    print(f'Total de procesos: {len(pids)}')

    for pid in pids[:5]:
        try:
            info = leer_proceso(pid)
            print(f"PID {info['pid']:>6} | {info['estado']} | "
                  f"{info['nombre']:<15} | RSS {info['vmrss_kb']:>12}")
        except (FileNotFoundError, ProcessLookupError):
            continue

    print('\n--- Sistema global ---')
    import pprint
    pprint.pprint(leer_sistema())
