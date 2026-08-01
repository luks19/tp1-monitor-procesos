"""display.py — TUI con rich. Compatible WSL2."""
import os
import sys
import time
import json
import threading
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich import box
from src.utils import dump_snapshot

console = Console()

TECLAS_VISTA = {
    '1': 'resumen', 'r': 'resumen',
    '2': 'memoria', 'm': 'memoria',
    '3': 'fds',     'f': 'fds',
    '4': 'threads', 't': 'threads',
    '5': 'senales', 's': 'senales',
    '6': 'scheduling', 'p': 'scheduling',
    '7': 'sistema', 'g': 'sistema',
}


def tabla_resumen(datos, seleccionado, filtro, orden):
    t = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    t.add_column("PID",    width=7,  justify="right")
    t.add_column("EST",    width=3)
    t.add_column("CPU%",   width=6,  justify="right")
    t.add_column("RSS(kB)",width=9,  justify="right")
    t.add_column("THRD",   width=5,  justify="right")
    t.add_column("NICE",   width=5,  justify="right")
    t.add_column("NOMBRE", width=15)
    t.add_column("COMANDO",           no_wrap=True)
    try:
        items = list(dict(datos).items())
    except Exception:
        return t
    if orden == 'cpu':
        items.sort(key=lambda x: x[1].get('cpu_pct', 0), reverse=True)
    elif orden == 'rss':
        items.sort(key=lambda x: int(str(x[1].get('vmrss_kb','0 kB')).split()[0]),
                   reverse=True)
    else:
        items.sort(key=lambda x: x[0])
    for pid, info in items:
        nombre = info.get('nombre', '')
        if filtro and filtro.lower() not in nombre.lower():
            continue
        estado = info.get('estado', '?')
        color = {'R':'green','S':'white','D':'red','T':'yellow','Z':'magenta'}.get(estado,'white')
        rss = str(info.get('vmrss_kb','0 kB')).split()[0]
        estilo = "bold yellow on grey15" if pid == seleccionado else ""
        t.add_row(str(pid), Text(estado, style=color),
                  str(info.get('cpu_pct', 0.0)), rss,
                  str(info.get('threads','')), str(info.get('nice','')),
                  nombre, info.get('cmdline','')[:50], style=estilo)
    return t


def tabla_memoria(datos, seleccionado):
    t = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    t.add_column("PID",    width=7, justify="right")
    t.add_column("VmSize", width=9, justify="right")
    t.add_column("VmRSS",  width=9, justify="right")
    t.add_column("VmData", width=9, justify="right")
    t.add_column("VmStk",  width=8, justify="right")
    t.add_column("VmSwap", width=8, justify="right")
    t.add_column("Heap",   width=8, justify="right")
    t.add_column("Stack",  width=8, justify="right")
    try:
        items = sorted(dict(datos).items())
    except Exception:
        return t
    for pid, info in items:
        segs = info.get('segmentos', {})
        estilo = "bold yellow on grey15" if pid == seleccionado else ""
        t.add_row(str(pid),
                  str(info.get('vmsize_kb','')).split()[0],
                  str(info.get('vmrss_kb','')).split()[0],
                  str(info.get('vmdata_kb','')).split()[0],
                  str(info.get('vmstk_kb','')).split()[0],
                  str(info.get('vmswap_kb','')).split()[0],
                  str(segs.get('heap',0)), str(segs.get('stack',0)),
                  style=estilo)
    return t


def tabla_fds(datos, seleccionado):
    t = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    t.add_column("PID",    width=7, justify="right")
    t.add_column("Total",  width=6, justify="right")
    t.add_column("Files",  width=6, justify="right")
    t.add_column("Sockets",width=8, justify="right")
    t.add_column("Pipes",  width=7, justify="right")
    t.add_column("TTYs",   width=6, justify="right")
    t.add_column("Detalle", no_wrap=True)
    try:
        items = sorted(dict(datos).items())
    except Exception:
        return t
    for pid, lista_fds in items:
        if not isinstance(lista_fds, list):
            continue
        total   = len(lista_fds)
        files   = sum(1 for f in lista_fds if f.get('tipo')=='file')
        sockets = sum(1 for f in lista_fds if f.get('tipo')=='socket')
        pipes   = sum(1 for f in lista_fds if f.get('tipo')=='pipe')
        ttys    = sum(1 for f in lista_fds if f.get('tipo')=='tty')
        det     = ', '.join(f"{f['fd']}:{f['destino'][:15]}" for f in lista_fds[:3])
        estilo  = "bold yellow on grey15" if pid == seleccionado else ""
        t.add_row(str(pid),str(total),str(files),str(sockets),
                  str(pipes),str(ttys),det,style=estilo)
    return t


def tabla_threads(datos, seleccionado):
    t = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    t.add_column("PID",   width=7, justify="right")
    t.add_column("TID",   width=7, justify="right")
    t.add_column("Nombre",width=15)
    t.add_column("Est",   width=4)
    t.add_column("utime", width=8, justify="right")
    t.add_column("stime", width=8, justify="right")
    t.add_column("CtxV",  width=7, justify="right")
    t.add_column("CtxI",  width=7, justify="right")
    try:
        items = sorted(dict(datos).items())
    except Exception:
        return t
    for pid, lista_th in items:
        if not isinstance(lista_th, list):
            continue
        for th in lista_th:
            estilo = "bold yellow on grey15" if pid == seleccionado else ""
            t.add_row(str(pid), str(th.get('tid','')), th.get('nombre',''),
                      th.get('estado',''), str(th.get('utime','')),
                      str(th.get('stime','')), str(th.get('ctx_voluntarios','')),
                      str(th.get('ctx_involuntarios','')), style=estilo)
    return t


def tabla_senales(datos, seleccionado):
    t = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    t.add_column("PID",        width=7, justify="right")
    t.add_column("Con handler",          no_wrap=False)
    t.add_column("Ignoradas",            no_wrap=False)
    t.add_column("Bloqueadas",           no_wrap=False)
    t.add_column("Pendientes",           no_wrap=False)
    try:
        items = sorted(dict(datos).items())
    except Exception:
        return t
    for pid, info in items:
        estilo = "bold yellow on grey15" if pid == seleccionado else ""
        t.add_row(str(pid),
                  ', '.join(info.get('con_handler',[])),
                  ', '.join(info.get('ignoradas',[])),
                  ', '.join(info.get('bloqueadas',[])),
                  ', '.join(info.get('pendientes_proceso',[])),
                  style=estilo)
    return t


def tabla_scheduling(datos, seleccionado):
    t = Table(box=box.SIMPLE, expand=True, header_style="bold cyan")
    t.add_column("PID",   width=7, justify="right")
    t.add_column("Nice",  width=6, justify="right")
    t.add_column("Prio",  width=6, justify="right")
    t.add_column("PGID",  width=7, justify="right")
    t.add_column("SID",   width=7, justify="right")
    t.add_column("CtxVol",width=8, justify="right")
    t.add_column("CtxInv",width=8, justify="right")
    try:
        items = sorted(dict(datos).items())
    except Exception:
        return t
    for pid, info in items:
        estilo = "bold yellow on grey15" if pid == seleccionado else ""
        t.add_row(str(pid), str(info.get('nice','')), str(info.get('priority','')),
                  str(info.get('pgid','')), str(info.get('sid','')),
                  str(info.get('ctx_voluntarios','')),
                  str(info.get('ctx_involuntarios','')), style=estilo)
    return t


def panel_sistema(datos):
    try:
        d = dict(datos)
    except Exception:
        return Panel("Sin datos aun...", title="Sistema Global")
    mem_total  = d.get('mem_total_kb', 0)
    mem_usada  = d.get('mem_usada_kb', 0)
    mem_pct    = round(mem_usada / mem_total * 100, 1) if mem_total else 0
    swap_total = d.get('swap_total_kb', 0)
    swap_libre = d.get('swap_libre_kb', 0)
    swap_pct   = round((swap_total-swap_libre)/swap_total*100,1) if swap_total else 0
    estados    = d.get('estados_procesos', {})
    zombies    = d.get('zombies', [])
    texto = (
        f"CPU:  {d.get('cpu_pct',0.0):>5.1f}%   "
        f"Load: {d.get('load_1min',0):.2f} / {d.get('load_5min',0):.2f} / {d.get('load_15min',0):.2f}\n"
        f"MEM:  {mem_usada//1024:>6} MB / {mem_total//1024} MB  ({mem_pct}%)\n"
        f"SWAP: {(swap_total-swap_libre)//1024:>6} MB / {swap_total//1024} MB  ({swap_pct}%)\n"
        f"Procs: R={estados.get('R',0)} S={estados.get('S',0)} "
        f"D={estados.get('D',0)} T={estados.get('T',0)} Z={estados.get('Z',0)}  "
        f"Zombies: {len(zombies)}\n"
        f"Corriendo: {d.get('procs_corriendo',0)} / {d.get('procs_totales',0)}"
    )
    return Panel(texto, title="[bold cyan]Sistema Global[/]", border_style="cyan")


def generar_pantalla(snapshot, vista, seleccionado, filtro, orden, intervalos):
    try:
        ts = snapshot[vista].get('ts', 0)
    except Exception:
        ts = 0
    ts_str = time.strftime('%H:%M:%S', time.localtime(ts)) if ts else '--:--:--'
    barra = (
        f"[bold]Monitor[/] | Vista:[cyan]{vista}[/] | "
        f"Orden:[yellow]{orden}[/] | {ts_str} | "
        f"Intervalo:{intervalos.get(vista,'?')}s | "
        f"[dim]1-7 vista  c orden  q salir[/]"
    )
    try:
        if vista == 'sistema':
            datos = dict(snapshot['sistema']['datos'])
            return Panel(panel_sistema(datos), title=barra, border_style="blue")
        datos = dict(snapshot[vista]['datos'])
    except Exception:
        datos = {}
    if vista == 'resumen':
        tabla = tabla_resumen(datos, seleccionado, filtro, orden)
    elif vista == 'memoria':
        tabla = tabla_memoria(datos, seleccionado)
    elif vista == 'fds':
        tabla = tabla_fds(datos, seleccionado)
    elif vista == 'threads':
        tabla = tabla_threads(datos, seleccionado)
    elif vista == 'senales':
        tabla = tabla_senales(datos, seleccionado)
    elif vista == 'scheduling':
        tabla = tabla_scheduling(datos, seleccionado)
    else:
        tabla = Table()
    return Panel(tabla, title=barra, border_style="blue")


def iniciar_tui(snapshot, stop_event, flag_dump, flag_verbose,
                flag_reload, intervalos, config_path):

    estado = {
        'vista': 'resumen',
        'seleccionado': None,
        'filtro': '',
        'orden': 'pid',
        'pids_lista': [],
        'idx': 0,
        'tecla': None,
        'lock': threading.Lock(),
    }

    def hilo_teclado():
        try:
            import termios, tty, fcntl, array
            tty_file = open('/dev/tty', 'rb', buffering=0)
            fd = tty_file.fileno()
            old = termios.tcgetattr(fd)
            # Vaciar buffer residual
            try:
                buf = array.array('i', [0])
                fcntl.ioctl(fd, termios.FIONREAD, buf)
                if buf[0] > 0:
                    tty_file.read(buf[0])
            except Exception:
                pass
            try:
                tty.setcbreak(fd)
                while not stop_event.is_set():
                    ch_bytes = tty_file.read(1)
                    if not ch_bytes:
                        continue
                    ch = ch_bytes.decode('utf-8', errors='ignore')
                    if ch == '\x1b':
                        try:
                            ch2 = tty_file.read(1).decode('utf-8', errors='ignore')
                            ch3 = tty_file.read(1).decode('utf-8', errors='ignore')
                            if ch2 == '[':
                                if ch3 == 'A': ch = 'UP'
                                elif ch3 == 'B': ch = 'DOWN'
                        except Exception:
                            pass
                    with estado['lock']:
                        estado['tecla'] = ch
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                tty_file.close()
        except Exception:
            pass

    t = threading.Thread(target=hilo_teclado, daemon=True)
    t.start()
    time.sleep(0.2)

    try:
        with Live(console=console, refresh_per_second=2, screen=True) as live:
            while not stop_event.is_set():

                if flag_dump.value:
                    flag_dump.value = 0
                    dump_snapshot(snapshot)

                if flag_reload.value:
                    flag_reload.value = 0
                    try:
                        with open(config_path) as f:
                            cfg = json.load(f)
                        intervalos.update(cfg.get('intervalos', {}))
                    except Exception:
                        pass

                with estado['lock']:
                    tecla = estado['tecla']
                    estado['tecla'] = None

                if tecla:
                    if tecla in ('q', '\x03', '\x04'):
                        stop_event.set()
                        break
                    elif tecla in TECLAS_VISTA:
                        estado['vista'] = TECLAS_VISTA[tecla]
                    elif tecla == 'UP':
                        estado['idx'] = max(0, estado['idx'] - 1)
                    elif tecla == 'DOWN':
                        estado['idx'] = min(
                            len(estado['pids_lista']) - 1,
                            estado['idx'] + 1)
                    elif tecla == 'c':
                        ciclo = ['pid', 'cpu', 'rss']
                        estado['orden'] = ciclo[
                            (ciclo.index(estado['orden']) + 1) % len(ciclo)]
                    elif tecla == '+':
                        v = estado['vista']
                        intervalos[v] = min(60.0, intervalos.get(v, 2.0) + 0.5)
                    elif tecla == '-':
                        v = estado['vista']
                        intervalos[v] = max(0.5, intervalos.get(v, 2.0) - 0.5)

                try:
                    pids = sorted(dict(snapshot['resumen']['datos']).keys())
                    estado['pids_lista'] = pids
                    if pids:
                        idx = min(estado['idx'], len(pids) - 1)
                        estado['seleccionado'] = pids[idx]
                except Exception:
                    pass

                contenido = generar_pantalla(
                    snapshot, estado['vista'], estado['seleccionado'],
                    estado['filtro'], estado['orden'], intervalos)
                live.update(contenido)
                time.sleep(0.4)

    except KeyboardInterrupt:
        stop_event.set()
