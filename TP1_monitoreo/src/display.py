import os
import sys
import tty
import termios
import select
import fcntl
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.live import Live

INTERVALOS_MINIMOS = {
    'resumen': 0.5,
    'threads': 0.5,
    'memoria': 1.0,
    'sistema': 1.0,
    'fds': 2.0,
    'senales': 5.0,
    'scheduling': 5.0
}

VISTAS = ['resumen', 'memoria', 'fds', 'senales', 'threads', 'scheduling', 'sistema']

def crear_panel_ayuda():
    ayuda_texto = Text()
    ayuda_texto.append("Comandos de Teclado:\n", style="bold cyan")
    ayuda_texto.append("  1-7 / c      : Cambiar de vista activa\n")
    ayuda_texto.append("  ↑ / ↓        : Navegar lista de procesos\n")
    ayuda_texto.append("  Enter        : Fijar / Desfijar PID seleccionado (Pin)\n")
    ayuda_texto.append("  /            : Filtrar por comando (escribir texto, Enter para confirmar)\n")
    ayuda_texto.append("  u            : Filtrar por usuario (escribir texto, Enter para confirmar)\n")
    ayuda_texto.append("  + / -        : Aumentar / Disminuir intervalo de la vista activa\n")
    ayuda_texto.append("  h / ?        : Mostrar / Ocultar este panel de ayuda\n")
    ayuda_texto.append("  q            : Salir del monitor de forma ordenada\n\n")
    ayuda_texto.append("Señales POSIX Soportadas:\n", style="bold yellow")
    ayuda_texto.append("  SIGHUP       : Recargar config.json y propagar intervalos a analizadores\n")
    ayuda_texto.append("  SIGUSR1      : Generar snapshot dump en archivo JSON\n")
    ayuda_texto.append("  SIGUSR2      : Toggle modo verbose (muestra hasta 20 FDs)\n")
    ayuda_texto.append("  SIGTERM/INT  : Finalización limpia de todos los procesos hijos\n")
    
    return Panel(ayuda_texto, title="[bold green]Ayuda y Referencia[/bold green]", border_style="green")

def tabla_resumen(datos, filtro_cmd, filtro_usr, indice_sel, pin_pid):
    tabla = Table(expand=True, box=None)
    tabla.add_column("PID", justify="right", style="cyan")
    tabla.add_column("USER", justify="left")
    tabla.add_column("PR", justify="right")
    tabla.add_column("NI", justify="right")
    tabla.add_column("RES", justify="right")
    tabla.add_column("S", justify="center")
    tabla.add_column("%CPU", justify="right", style="green")
    tabla.add_column("POLICY", justify="left")
    tabla.add_column("MINFLT", justify="right")
    tabla.add_column("MAJFLT", justify="right")
    tabla.add_column("COMMAND", justify="left")

    procs = datos.get('procesos', [])
    if filtro_cmd:
        procs = [p for p in procs if filtro_cmd.lower() in p['command'].lower()]
    if filtro_usr:
        procs = [p for p in procs if filtro_usr.lower() in p['usuario'].lower()]

    for i, p in enumerate(procs[:25]):
        es_pin = (pin_pid == p['pid'])
        es_cursor = (i == indice_sel)
        
        estilo = "bold white on blue" if es_cursor else ("bold yellow" if es_pin else None)
        marca_pin = " *" if es_pin else ""
        
        tabla.add_row(
            f"{p['pid']}{marca_pin}",
            str(p['usuario']),
            str(p['priority']),
            str(p['nice']),
            str(p['vm_rss']),
            str(p['state']),
            f"{p['cpu_pct']:.1f}",
            str(p.get('policy', 'OTHER')),
            str(p.get('minflt', 0)),
            str(p.get('majflt', 0)),
            p['command'][:40],
            style=estilo
        )
    return tabla, procs

def tabla_memoria(datos, filtro_cmd, filtro_usr, indice_sel, pin_pid):
    tabla = Table(expand=True, box=None)
    tabla.add_column("PID", justify="right", style="cyan")
    tabla.add_column("NOMBRE", justify="left")
    tabla.add_column("VmSize", justify="right")
    tabla.add_column("VmRSS", justify="right")
    tabla.add_column("VmHWM", justify="right")
    tabla.add_column("HEAP (KB)", justify="right")
    tabla.add_column("STACK (KB)", justify="right")
    tabla.add_column("SO (KB)", justify="right")
    tabla.add_column("TOTAL (KB)", justify="right", style="green")

    procs = datos.get('procesos', [])
    if filtro_cmd:
        procs = [p for p in procs if filtro_cmd.lower() in p['nombre'].lower()]

    for i, p in enumerate(procs[:25]):
        es_pin = (pin_pid == p['pid'])
        es_cursor = (i == indice_sel)
        estilo = "bold white on blue" if es_cursor else ("bold yellow" if es_pin else None)
        marca_pin = " *" if es_pin else ""

        tabla.add_row(
            f"{p['pid']}{marca_pin}",
            p['nombre'][:25],
            str(p.get('vm_size', '0 kB')),
            str(p.get('vm_rss', '0 kB')),
            str(p.get('vm_hwm', '0 kB')),
            str(p['heap_kb']),
            str(p['stack_kb']),
            str(p['so_kb']),
            str(p['total_kb']),
            style=estilo
        )
    return tabla, procs

def tabla_fds(datos, filtro_cmd, indice_sel, pin_pid, modo_verbose):
    tabla = Table(expand=True, box=None)
    tabla.add_column("PID", justify="right", style="cyan")
    tabla.add_column("NOMBRE", justify="left")
    tabla.add_column("TOTAL FDs", justify="right", style="magenta")
    tabla.add_column("DESCRIPTORES (FD -> DESTINO)", justify="left")

    procs = datos.get('procesos', [])
    if filtro_cmd:
        procs = [p for p in procs if filtro_cmd.lower() in p['nombre'].lower()]

    limite_fds = 20 if modo_verbose else 3

    for i, p in enumerate(procs[:20]):
        es_pin = (pin_pid == p['pid'])
        es_cursor = (i == indice_sel)
        estilo = "bold white on blue" if es_cursor else ("bold yellow" if es_pin else None)
        marca_pin = " *" if es_pin else ""

        lista_fds = p.get('fds', [])
        str_fds = ", ".join([f"{fd['fd']}->{fd['destino'][:20]}" for fd in lista_fds[:limite_fds]])
        if len(lista_fds) > limite_fds:
            str_fds += f" ... (+{len(lista_fds) - limite_fds} más)"

        tabla.add_row(
            f"{p['pid']}{marca_pin}",
            p['nombre'][:20],
            str(p['cantidad_fds']),
            str_fds,
            style=estilo
        )
    return tabla, procs

def tabla_senales(datos, filtro_cmd, indice_sel, pin_pid):
    tabla = Table(expand=True, box=None)
    tabla.add_column("PID", justify="right", style="cyan")
    tabla.add_column("NOMBRE", justify="left")
    tabla.add_column("BLOQUEADAS (SigBlk)", justify="left")
    tabla.add_column("IGNORADAS (SigIgn)", justify="left")
    tabla.add_column("CON HANDLER (SigCgt)", justify="left")

    procs = datos.get('procesos', [])
    if filtro_cmd:
        procs = [p for p in procs if filtro_cmd.lower() in p['nombre'].lower()]

    for i, p in enumerate(procs[:20]):
        es_pin = (pin_pid == p['pid'])
        es_cursor = (i == indice_sel)
        estilo = "bold white on blue" if es_cursor else ("bold yellow" if es_pin else None)
        marca_pin = " *" if es_pin else ""

        blk = ", ".join(p['bloqueadas'][:4]) + ("..." if len(p['bloqueadas']) > 4 else "")
        ign = ", ".join(p['ignoradas'][:4]) + ("..." if len(p['ignoradas']) > 4 else "")
        cgt = ", ".join(p['con_handler'][:4]) + ("..." if len(p['con_handler']) > 4 else "")

        tabla.add_row(
            f"{p['pid']}{marca_pin}",
            p['nombre'][:20],
            blk if blk else "-",
            ign if ign else "-",
            cgt if cgt else "-",
            style=estilo
        )
    return tabla, procs

def tabla_threads(datos, filtro_cmd, indice_sel, pin_pid):
    tabla = Table(expand=True, box=None)
    tabla.add_column("PID", justify="right", style="cyan")
    tabla.add_column("NOMBRE", justify="left")
    tabla.add_column("THREADS", justify="right", style="magenta")
    tabla.add_column("ESTADO", justify="center")
    tabla.add_column("PRIORITY", justify="right")
    tabla.add_column("NICE", justify="right")

    procs = datos.get('procesos', [])
    if filtro_cmd:
        procs = [p for p in procs if filtro_cmd.lower() in p['nombre'].lower()]

    for i, p in enumerate(procs[:25]):
        es_pin = (pin_pid == p['pid'])
        es_cursor = (i == indice_sel)
        estilo = "bold white on blue" if es_cursor else ("bold yellow" if es_pin else None)
        marca_pin = " *" if es_pin else ""

        tabla.add_row(
            f"{p['pid']}{marca_pin}",
            p['nombre'][:30],
            str(p['num_threads']),
            str(p['state']),
            str(p['priority']),
            str(p['nice']),
            style=estilo
        )
    return tabla, procs

def tabla_scheduling(datos, filtro_cmd, indice_sel, pin_pid):
    tabla = Table(expand=True, box=None)
    tabla.add_column("PID", justify="right", style="cyan")
    tabla.add_column("NOMBRE", justify="left")
    tabla.add_column("POLICY", justify="left", style="green")
    tabla.add_column("PRIORITY", justify="right")
    tabla.add_column("RT_PRIO", justify="right")
    tabla.add_column("NICE", justify="right")
    tabla.add_column("CPUS ALLOWED", justify="left")

    procs = datos.get('procesos', [])
    if filtro_cmd:
        procs = [p for p in procs if filtro_cmd.lower() in p['nombre'].lower()]

    for i, p in enumerate(procs[:25]):
        es_pin = (pin_pid == p['pid'])
        es_cursor = (i == indice_sel)
        estilo = "bold white on blue" if es_cursor else ("bold yellow" if es_pin else None)
        marca_pin = " *" if es_pin else ""

        tabla.add_row(
            f"{p['pid']}{marca_pin}",
            p['nombre'][:30],
            str(p.get('policy', 'OTHER')),
            str(p['priority']),
            str(p.get('rt_priority', 0)),
            str(p['nice']),
            str(p.get('cpus_allowed', ''))[:20],
            style=estilo
        )
    return tabla, procs

def tabla_sistema(datos):
    tabla = Table(expand=True, box=None)
    tabla.add_column("Métrica", justify="left", style="cyan")
    tabla.add_column("Valor", justify="left", style="green")

    tabla.add_row("Total de Procesos", str(datos.get('total_procesos', 0)))
    tabla.add_row("Uptime del Sistema", f"{datos.get('uptime', 0.0):.1f} segundos")
    tabla.add_row("Memoria Total", str(datos.get('mem_total', '0 kB')))
    tabla.add_row("Memoria Libre", str(datos.get('mem_free', '0 kB')))
    tabla.add_row("Memoria Disponible", str(datos.get('mem_available', '0 kB')))

    estados = datos.get('estados', {})
    str_estados = ", ".join([f"{k}: {v}" for k, v in estados.items()])
    tabla.add_row("Distribución de Estados", str_estados if str_estados else "-")
    return tabla, []

def generar_pantalla(vista_actual, snapshot_dict, intervalos_sync, flag_verbose, estado):
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3)
    )

    intervalo_actual = intervalos_sync[vista_actual].value
    modo_v = bool(flag_verbose.value)
    badge_verbose = "[bold green][VERBOSE: ON][/bold green]" if modo_v else "[dim][VERBOSE: OFF][/dim]"
    
    pin_info = f" | PIN: [yellow]PID {estado['pin_pid']}[/yellow]" if estado['pin_pid'] else ""
    filtro_info = f" | FILTRO: '{estado['filtro_cmd']}'" if estado['filtro_cmd'] else ""
    usr_info = f" | USER: '{estado['filtro_usr']}'" if estado['filtro_usr'] else ""

    header_text = (
        f"[bold cyan]MONITOR DE PROCESOS[/bold cyan] | Vista: [bold white on blue] {vista_actual.upper()} [/bold white on blue] "
        f"| Intervalo: [bold]{intervalo_actual:.1f}s[/bold] {badge_verbose}{pin_info}{filtro_info}{usr_info}"
    )
    layout["header"].update(Panel(header_text, style="white on black"))

    if estado['mostrar_ayuda']:
        layout["body"].update(crear_panel_ayuda())
        lista_actual = []
    else:
        datos_vista = snapshot_dict.get(vista_actual, {})
        if vista_actual == 'resumen':
            tabla, lista_actual = tabla_resumen(datos_vista, estado['filtro_cmd'], estado['filtro_usr'], estado['indice_sel'], estado['pin_pid'])
        elif vista_actual == 'memoria':
            tabla, lista_actual = tabla_memoria(datos_vista, estado['filtro_cmd'], estado['filtro_usr'], estado['indice_sel'], estado['pin_pid'])
        elif vista_actual == 'fds':
            tabla, lista_actual = tabla_fds(datos_vista, estado['filtro_cmd'], estado['indice_sel'], estado['pin_pid'], modo_v)
        elif vista_actual == 'senales':
            tabla, lista_actual = tabla_senales(datos_vista, estado['filtro_cmd'], estado['indice_sel'], estado['pin_pid'])
        elif vista_actual == 'threads':
            tabla, lista_actual = tabla_threads(datos_vista, estado['filtro_cmd'], estado['indice_sel'], estado['pin_pid'])
        elif vista_actual == 'scheduling':
            tabla, lista_actual = tabla_scheduling(datos_vista, estado['filtro_cmd'], estado['indice_sel'], estado['pin_pid'])
        elif vista_actual == 'sistema':
            tabla, lista_actual = tabla_sistema(datos_vista)
        else:
            tabla = Table()
            lista_actual = []

        layout["body"].update(Panel(tabla, border_style="blue"))

    if estado['modo_input']:
        prompt = "Filtrar por Comando: " if estado['modo_input'] == 'cmd' else "Filtrar por Usuario: "
        footer_text = f"[bold yellow]{prompt}[/bold yellow]{estado['buffer_input']}_  [dim](Enter: confirmar, Esc: cancelar)[/dim]"
    else:
        footer_text = "[bold]q[/bold]: Salir | [bold]1-7/c[/bold]: Vista | [bold]+/-[/bold]: Intervalo | [bold]Enter[/bold]: Pin | [bold]/[/bold]: Filtro | [bold]u[/bold]: User | [bold]h/?[/bold]: Ayuda"
    
    layout["footer"].update(Panel(footer_text, style="white on black"))
    return layout, lista_actual

def leer_tecla_no_bloqueante(tty_fd):
    try:
        dr, _, _ = select.select([tty_fd], [], [], 0.05)
        if dr:
            return os.read(tty_fd, 32).decode('utf-8', errors='ignore')
    except Exception:
        pass
    return None

def iniciar_tui(snapshot_dict, intervalos_sync, flag_verbose, stop_event):
    console = Console()
    vista_idx = 0
    
    estado = {
        'indice_sel': 0,
        'pin_pid': None,
        'filtro_cmd': '',
        'filtro_usr': '',
        'mostrar_ayuda': False,
        'modo_input': None,
        'buffer_input': ''
    }

    # Abrir directamente /dev/tty para control exclusivo del teclado sin colisionar con buffers
    tty_fd = os.open('/dev/tty', os.O_RDWR)
    old_settings = termios.tcgetattr(tty_fd)

    try:
        tty.setcbreak(tty_fd)
        with Live(console=console, screen=True, auto_refresh=False) as live:
            while not stop_event.is_set():
                vista_actual = VISTAS[vista_idx]
                pantalla, procs_actuales = generar_pantalla(
                    vista_actual, snapshot_dict, intervalos_sync, flag_verbose, estado
                )
                
                live.update(pantalla, refresh=True)

                tecla = leer_tecla_no_bloqueante(tty_fd)
                if not tecla:
                    time.sleep(0.1)
                    continue

                # Modo de edición de filtros
                if estado['modo_input']:
                    if tecla in ('\r', '\n'):
                        if estado['modo_input'] == 'cmd':
                            estado['filtro_cmd'] = estado['buffer_input']
                        elif estado['modo_input'] == 'usr':
                            estado['filtro_usr'] = estado['buffer_input']
                        estado['modo_input'] = None
                        estado['buffer_input'] = ''
                    elif tecla == '\x1b':
                        estado['modo_input'] = None
                        estado['buffer_input'] = ''
                    elif tecla in ('\x7f', '\x08'):
                        estado['buffer_input'] = estado['buffer_input'][:-1]
                    elif tecla.isprintable():
                        estado['buffer_input'] += tecla
                    continue

                # Atajos en modo normal
                if tecla == 'q':
                    stop_event.set()
                    break
                elif tecla in ('h', '?'):
                    estado['mostrar_ayuda'] = not estado['mostrar_ayuda']
                elif tecla == 'c':
                    vista_idx = (vista_idx + 1) % len(VISTAS)
                    estado['indice_sel'] = 0
                elif tecla in ('1', '2', '3', '4', '5', '6', '7'):
                    vista_idx = int(tecla) - 1
                    estado['indice_sel'] = 0
                elif tecla == '+':
                    intervalos_sync[vista_actual].value = round(intervalos_sync[vista_actual].value + 0.5, 1)
                elif tecla == '-':
                    minimo = INTERVALOS_MINIMOS.get(vista_actual, 0.5)
                    intervalos_sync[vista_actual].value = max(minimo, round(intervalos_sync[vista_actual].value - 0.5, 1))
                elif tecla == '\x1b[A':  # Flecha Arriba
                    estado['indice_sel'] = max(0, estado['indice_sel'] - 1)
                elif tecla == '\x1b[B':  # Flecha Abajo
                    if procs_actuales:
                        estado['indice_sel'] = min(len(procs_actuales) - 1, estado['indice_sel'] + 1)
                elif tecla in ('\r', '\n'):  # Enter -> Pin PID
                    if procs_actuales and estado['indice_sel'] < len(procs_actuales):
                        pid_sel = procs_actuales[estado['indice_sel']]['pid']
                        estado['pin_pid'] = None if estado['pin_pid'] == pid_sel else pid_sel
                elif tecla == '/':
                    estado['modo_input'] = 'cmd'
                    estado['buffer_input'] = estado['filtro_cmd']
                elif tecla == 'u':
                    estado['modo_input'] = 'usr'
                    estado['buffer_input'] = estado['filtro_usr']

                time.sleep(0.05)
    finally:
        termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_settings)
        os.close(tty_fd)