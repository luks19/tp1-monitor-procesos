def leer_status(pid):
    """Lee /proc/<pid>/status y devuelve un dict con los campos clave."""
    datos = {}
    with open(f'/proc/{pid}/status', 'r') as f:
        for linea in f:
            # Cada línea tiene forma "Clave:\tValor\n"
            clave, _, valor = linea.partition(':')
            datos[clave.strip()] = valor.strip()

    return {
        'nombre': datos['Name'],
        'estado_raw': datos['State'],
        'ppid': int(datos['PPid']),
        'threads': int(datos['Threads']),
        'vmrss_kb': datos.get('VmRSS', '0 kB'),
        'vmsize_kb': datos.get('VmSize', '0 kB'),
        'sigblk': datos.get('SigBlk', '0'),
        'sigcgt': datos.get('SigCgt', '0'),
    }


if __name__ == '__main__':
    import os
    import pprint
    pprint.pprint(leer_status(os.getpid()))
