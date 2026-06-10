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
    # cmdline separa los argumentos con bytes nulos (\x00)
    partes = contenido.split(b'\x00')
    partes = [p.decode('utf-8', errors='replace') for p in partes if p]
    return ' '.join(partes)


def leer_proceso(pid):
    """Combina stat + status + cmdline en un solo dict para un proceso."""
    info = {}
    info.update(leer_stat(pid))
    info.update(leer_status(pid))
    try:
        info['cmdline'] = leer_cmdline(pid)
    except Exception:
        info['cmdline'] = f'[{info["nombre"]}]'  # procesos kernel no tienen cmdline
    return info


if __name__ == '__main__':
    # Prueba: listar todos los procesos y mostrar los primeros 5
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
            # El proceso pudo haber terminado entre listar_pids() y leerlo
            continue
