import os
import signal

POLICIES = {
    0: 'OTHER',
    1: 'FIFO',
    2: 'RR',
    3: 'BATCH',
    5: 'IDLE',
    6: 'DEADLINE'
}

def obtener_usuarios():
    usuarios = {}
    try:
        with open('/etc/passwd', 'r') as f:
            for linea in f:
                partes = linea.strip().split(':')
                if len(partes) >= 3:
                    try:
                        usuarios[int(partes[2])] = partes[0]
                    except ValueError:
                        continue
    except Exception:
        pass
    return usuarios

USUARIOS_CACHE = obtener_usuarios()

def listar_pids():
    pids = []
    try:
        for entrada in os.listdir('/proc'):
            if entrada.isdigit():
                pids.append(int(entrada))
    except Exception:
        pass
    return pids

def leer_stat(pid):
    try:
        with open(f'/proc/{pid}/stat', 'r') as f:
            contenido = f.read()
        
        inicio_comm = contenido.find('(')
        fin_comm = contenido.rfind(')')
        if inicio_comm == -1 or fin_comm == -1:
            return None
        
        comm = contenido[inicio_comm + 1:fin_comm]
        resto = contenido[fin_comm + 2:].split()
        
        policy_num = int(resto[38]) if len(resto) > 38 else 0
        policy_str = POLICIES.get(policy_num, str(policy_num))
        rt_prio = int(resto[37]) if len(resto) > 37 else 0

        return {
            'pid': pid,
            'comm': comm,
            'state': resto[0],
            'ppid': int(resto[1]),
            'minflt': int(resto[7]),
            'majflt': int(resto[9]),
            'utime': int(resto[11]),
            'stime': int(resto[12]),
            'priority': int(resto[15]),
            'nice': int(resto[16]),
            'num_threads': int(resto[17]),
            'rt_priority': rt_prio,
            'policy': policy_str
        }
    except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError, ValueError):
        return None

def leer_status(pid):
    try:
        datos = {}
        with open(f'/proc/{pid}/status', 'r') as f:
            for linea in f:
                clave, _, valor = linea.partition(':')
                datos[clave.strip()] = valor.strip()
        
        uid_str = datos.get('Uid', '').split()
        uid_real = int(uid_str[0]) if uid_str else 0
        usuario_nom = USUARIOS_CACHE.get(uid_real, str(uid_real))
        
        gid_str = datos.get('Gid', '').split()
        gid_real = int(gid_str[0]) if gid_str else 0

        return {
            'pid': pid,
            'name': datos.get('Name', ''),
            'state': datos.get('State', ''),
            'uid': uid_real,
            'usuario': usuario_nom,
            'gid': gid_real,
            'vm_size': datos.get('VmSize', '0 kB'),
            'vm_rss': datos.get('VmRSS', '0 kB'),
            'vm_hwm': datos.get('VmHWM', '0 kB'),
            'threads': int(datos.get('Threads', 1)),
            'cpus_allowed_list': datos.get('Cpus_allowed_list', ''),
            'sig_blk': datos.get('SigBlk', '0'),
            'sig_ign': datos.get('SigIgn', '0'),
            'sig_cgt': datos.get('SigCgt', '0'),
            'sig_pnd': datos.get('SigPnd', '0'),
            'shd_pnd': datos.get('ShdPnd', '0')
        }
    except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError, ValueError):
        return None

def leer_cmdline(pid):
    try:
        with open(f'/proc/{pid}/cmdline', 'rb') as f:
            contenido = f.read()
        args = contenido.decode('utf-8', errors='replace').split('\x00')
        cmd = " ".join([a for a in args if a])
        return cmd if cmd else None
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None

def leer_maps(pid):
    try:
        regiones = {
            'heap_kb': 0,
            'stack_kb': 0,
            'so_kb': 0,
            'bin_kb': 0,
            'otros_kb': 0,
            'total_kb': 0
        }
        with open(f'/proc/{pid}/maps', 'r') as f:
            for linea in f:
                partes = linea.split()
                if len(partes) < 5:
                    continue
                rango = partes[0].split('-')
                inicio = int(rango[0], 16)
                fin = int(rango[1], 16)
                tam_kb = (fin - inicio) // 1024
                
                pathname = partes[5] if len(partes) >= 6 else ''
                perms = partes[1]
                
                regiones['total_kb'] += tam_kb
                if pathname == '[heap]':
                    regiones['heap_kb'] += tam_kb
                elif pathname == '[stack]':
                    regiones['stack_kb'] += tam_kb
                elif '.so' in pathname:
                    regiones['so_kb'] += tam_kb
                elif pathname.startswith('/') and 'x' in perms:
                    regiones['bin_kb'] += tam_kb
                else:
                    regiones['otros_kb'] += tam_kb
        return regiones
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None

def leer_fds(pid):
    fds = []
    path_fd = f'/proc/{pid}/fd'
    try:
        for fd_nombre in os.listdir(path_fd):
            ruta_enlace = os.path.join(path_fd, fd_nombre)
            try:
                destino = os.readlink(ruta_enlace)
                fds.append({'fd': fd_nombre, 'destino': destino})
            except (FileNotFoundError, PermissionError):
                continue
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    return fds

def decodificar_senales(hex_mascara):
    try:
        valor = int(hex_mascara, 16)
    except ValueError:
        return []
    
    nombres = []
    for sig in range(1, 65):
        if valor & (1 << (sig - 1)):
            try:
                nom = signal.Signals(sig).name
            except ValueError:
                nom = f'SIG_{sig}'
            nombres.append(nom)
    return nombres