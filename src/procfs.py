"""
procfs.py — Funciones para leer datos de procesos desde /proc.
"""
import os


def listar_pids():
    """Devuelve la lista de PIDs activos en el sistema."""
    pids = []
    for entrada in os.listdir('/proc'):
        if entrada.isdigit():
            pids.append(int(entrada))
    return pids


def leer_stat(pid):
    """Lee /proc/<pid>/stat. Lanza FileNotFoundError si el proceso ya no existe."""
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


def leer_status(pid):
    """Lee /proc/<pid>/status."""
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
    """Lee /proc/<pid>/cmdline y devuelve el comando completo como string."""
    with open(f'/proc/{pid}/cmdline', 'rb') as f:
        contenido = f.read()
    partes = contenido.split(b'\x00')
    partes = [p.decode('utf-8', errors='replace') for p in partes if p]
    return ' '.join(partes)


def leer_maps(pid):
    """
    Lee /proc/<pid>/maps y agrupa los segmentos de memoria por categoria.
    Devuelve un dict {categoria: tamaño_total_kb}.
    """
    grupos = {
        'text': 0,
        'heap': 0,
        'stack': 0,
        'data': 0,
        'anonima': 0,
        'shared': 0,
        'otros': 0,
    }

    with open(f'/proc/{pid}/maps', 'r') as f:
        for linea in f:
            partes = linea.split(None, 5)
            rango = partes[0]
            permisos = partes[1]
            path = partes[5].strip() if len(partes) > 5 else ''

            inicio_str, fin_str = rango.split('-')
            tamaño_bytes = int(fin_str, 16) - int(inicio_str, 16)
            tamaño_kb = tamaño_bytes // 1024

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


def leer_proceso(pid):
    """Combina stat + status + cmdline en un solo dict para un proceso."""
    info = {}
    info.update(leer_stat(pid))
    info.update(leer_status(pid))
    try:
        info['cmdline'] = leer_cmdline(pid)
    except Exception:
        info['cmdline'] = f'[{info["nombre"]}]'
    return info


def listar_threads(pid):
    """
    Lee /proc/<pid>/task/ y devuelve una lista de dicts con info de cada thread.
    """
    threads = []
    ruta_task = f'/proc/{pid}/task'

    for tid_str in os.listdir(ruta_task):
        tid = int(tid_str)
        try:
            # El stat de un thread tiene el mismo formato que el de un proceso
            info_stat = leer_stat_en_ruta(f'{ruta_task}/{tid_str}/stat')

            # comm: nombre del thread (puede diferir del nombre del proceso)
            with open(f'{ruta_task}/{tid_str}/comm', 'r') as f:
                nombre_thread = f.read().strip()

            # Context switches del thread, desde su status
            ctx_vol, ctx_invol = leer_context_switches(f'{ruta_task}/{tid_str}/status')

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
            # El thread pudo terminar entre el listdir y la lectura
            continue

    return threads


def leer_stat_en_ruta(ruta):
    """Igual que leer_stat pero recibe la ruta completa (sirve para threads)."""
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


def leer_context_switches(ruta_status):
    """Lee voluntary_ctxt_switches y nonvoluntary_ctxt_switches de un status."""
    vol, invol = 0, 0
    with open(ruta_status, 'r') as f:
        for linea in f:
            if linea.startswith('voluntary_ctxt_switches'):
                vol = int(linea.split(':')[1].strip())
            elif linea.startswith('nonvoluntary_ctxt_switches'):
                invol = int(linea.split(':')[1].strip())
    return vol, invol


if __name__ == '__main__':
    pids = listar_pids()
    print(f'Total de procesos encontrados: {len(pids)}')

    contador = 0
    for pid in pids:
        try:
            info = leer_proceso(pid)
            print(f"PID {info['pid']:>6} | {info['estado']} | "
                  f"PPID {info['ppid']:>6} | {info['nombre']:<15} | "
                  f"RSS {info['vmrss_kb']:>12} | {info['cmdline'][:40]}")
            contador += 1
            if contador >= 5:
                break
        except (FileNotFoundError, ProcessLookupError):
            continue

    print('\n--- Segmentos de memoria del propio proceso ---')
    print(leer_maps(os.getpid()))

    print('\n--- Threads del propio proceso ---')
    for t in listar_threads(os.getpid()):
        print(t)
