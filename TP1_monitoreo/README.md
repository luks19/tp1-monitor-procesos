# TP1 — Monitor de Procesos y Threads en Linux

Monitor de procesos y threads del sistema operativo Linux en tiempo real implementado en Python 3 sobre arquitectura multiproceso POSIX, sin dependencias de bibliotecas de terceros para la extracción de métricas del kernel (`/proc`).

---

## Arquitectura del Sistema

El sistema implementa un modelo concurrente desacoplado basado en procesos independientes:

- **Analizadores Paralelos:** Siete procesos independientes (`multiprocessing.Process`) recolectan información específica desde `/proc` (`resumen`, `memoria`, `fds`, `senales`, `threads`, `scheduling`, `sistema`). Cada worker relista dinámicamente los PIDs en cada ciclo y duerme a su propio ritmo.
- **Memoria Compartida y Sincronización:**
  - Los intervalos de muestreo se gestionan mediante escalares compartidos en memoria (`multiprocessing.Value('d', ...)`), permitiendo la actualización dinámica y atómica desde la TUI o ante señales del sistema.
  - Los handlers de señales encolan el número recibido en una `queue.SimpleQueue`; un hilo coordinador realiza después la recarga de configuración, el volcado o el cierre.
  - Los datos analizados se centralizan en un diccionario administrado por `multiprocessing.Manager`.
  - La terminación limpia y coordinada se realiza mediante un `multiprocessing.Event` (`stop_event`).
- **Interfaz de Usuario (TUI):** Renderizado en terminal con `rich` utilizando entrada no bloqueante por `/dev/tty` con `termios` en modo cbreak.

```text
main.py ── crea ──> analizadores (7 procesos) ── leen ──> /proc
   │                       │
   │                       └── publican snapshots ──> Manager.dict ──> TUI
   ├── comparte intervalos con Value <───────────────────────────────┘
   └── handlers ──> SimpleQueue ──> hilo coordinador (reload/dump/cierre)
```

### Decisiones de diseño

Cada analizador corre en un proceso separado porque las vistas se actualizan a ritmos distintos. `multiprocessing.Value` sirve para los intervalos, que son números pequeños y de tamaño fijo. Los snapshots contienen diccionarios y listas de tamaño variable; por eso se publican por vista en un `Manager.dict`. El `Event` comunica el cierre ordenado.

Cada analizador reemplaza su propia entrada del diccionario con un snapshot nuevo. Los lectores no modifican los datos publicados. Los procesos pueden desaparecer mientras se leen sus archivos de `/proc`; los lectores toleran esos errores y continúan. Las vistas se actualizan independientemente, por lo que sus timestamps no representan una única lectura simultánea del sistema.

Los handlers solo encolan la señal recibida. El hilo coordinador realiza el trabajo posterior, como leer `config.json` o escribir el dump, fuera del handler.

---

## Vistas Disponibles

La interfaz mantiene una lista resumida de procesos en la parte superior y muestra debajo el detalle de la vista activa para el proceso seleccionado.

1. **Resumen (`resumen`):** PID, PPID, usuario, prioridad, nice, RSS, estado, CPU%, cantidad de threads, política y fallos de página.
2. **Memoria (`memoria`):** `VmSize`, `VmRSS`, `VmHWM`, `VmData`, `VmStk`, `VmExe`, `VmLib`, `VmSwap`, fallos de página y regiones de `/proc/<pid>/maps` agrupadas como text, data, heap, stack y shared.
3. **Descriptores de Archivos (`fds`):** Cantidad de FDs, destino de cada enlace simbólico y tipo inferido (TTY, socket, pipe, archivo u otro).
4. **Threads (`threads`):** Lista de TID por proceso, nombre, estado, CPU% y cambios de contexto voluntarios e involuntarios.
5. **Señales (`senales`):** Máscaras decodificadas de señales bloqueadas, ignoradas, con manejador y pendientes (del proceso y compartidas).
6. **Scheduling (`scheduling`):** Política, prioridad, prioridad RT, nice, afinidad de CPU, cambios de contexto y datos de PPID, PGID y SID.
7. **Sistema (`sistema`):** CPU global, memoria y swap, load average, uptime y hora de inicio, totales de procesos, threads y zombies, y los tres procesos con más CPU y memoria.

### Conceptos del curso aplicados

- **Procesos e IPC:** los analizadores son procesos independientes y comparten intervalos con `Value`, snapshots con `Manager.dict` y el evento de cierre con `Event`.
- **Threads y procesos:** `/proc/<pid>/task/<tid>` permite distinguir el PID del proceso de los TID de sus threads.
- **Scheduling:** `stat` y `status` aportan política, prioridad, nice, afinidad y cambios de contexto.
- **Señales:** las máscaras de `/proc/<pid>/status` se decodifican bit a bit; las dirigidas al monitor se procesan mediante la cola y el hilo coordinador.
- **Uso de CPU:** el porcentaje se calcula con deltas de jiffies y el valor de `SC_CLK_TCK` del sistema.

---

## Controles e Interacción (Keybindings)

| Tecla | Acción |
| :--- | :--- |
| `1` - `7` / `r`, `m`, `f`, `t`, `s`, `p`, `g` | Cambiar entre vistas (Resumen, Memoria, FDs, Threads, Señales, Scheduling, Sistema) |
| `c` | Alternar el orden de la lista: CPU%, RSS y PID |
| `↑` / `↓` | Navegar la lista de procesos |
| `Enter` | Fijar / Desfijar (Pin) el PID seleccionado |
| `/` | Modo interactivo: filtrar procesos por nombre de comando (`COMMAND`) |
| `u` | Modo interactivo: filtrar procesos por usuario (`USER`) |
| `+` | Incrementar el intervalo de actualización de la vista actual (+0.5s) |
| `-` | Decrementar el intervalo de actualización respetando los límites mínimos |
| `h` / `?` | Abrir / Cerrar el panel modal de ayuda |
| `q` | Finalizar el monitor y cerrar ordenadamente todos los procesos hijos |

---

## Señales POSIX Soportadas

- **`SIGHUP` (`kill -HUP <PID>`):** Relee `config.json`, actualiza los intervalos compartidos respetando los mínimos y aplica los filtros predeterminados de comando y usuario.
- **`SIGUSR1` (`kill -USR1 <PID>`):** Genera un volcado completo de la instantánea actual del sistema en formato JSON (`dump_<timestamp>.json`).
- **`SIGUSR2` (`kill -USR2 <PID>`):** Alterna el modo *verbose* en pantalla, expandiendo la visualización de descriptores de archivos (de 3 a 20 FDs visibles).
- **`SIGTERM` / `SIGINT`:** Despierta a los analizadores mediante `stop_event`, espera su terminación (`join`) y cierra el `Manager` sin dejar procesos huérfanos.

---

## Intervalos Predeterminados y Mínimos

Los valores iniciales están en `config.json`. `+` y `-` modifican el intervalo de la vista activa; `-` respeta estos mínimos.

| Vista | Predeterminado | Mínimo |
| :--- | ---: | ---: |
| `resumen` | 2s | 0.5s |
| `memoria` | 3s | 1s |
| `fds` | 5s | 2s |
| `threads` | 2s | 0.5s |
| `senales` | 10s | 5s |
| `scheduling` | 10s | 5s |
| `sistema` | 2s | 1s |

El archivo también admite `filtro_cmd` y `filtro_usr` como filtros predeterminados; ambos son cadenas vacías si no se especifican.

## Limitaciones conocidas

- El monitor depende de `/proc` y está pensado para Linux; la visibilidad de algunos datos depende de los permisos del proceso que lo ejecuta.
- Los procesos pueden terminar entre la enumeración de PID y la lectura de sus archivos, por lo que alguna fila puede faltar en un ciclo.
- Las vistas tienen intervalos independientes y pueden mostrar timestamps distintos.
- El primer cálculo de CPU sirve como referencia; los porcentajes aparecen al comparar una lectura posterior.

---

## Ejecución

Con Python, desde la raíz del repositorio:

```bash
cd TP1_monitoreo
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python src/main.py
```

Para ejecutar las pruebas (con `pytest` instalado), desde la raíz del repositorio:

```bash
python3 -m pytest TP1_monitoreo/tests
```

El monitor requiere Linux o WSL y una terminal interactiva. Mantener `TP1_monitoreo/` como directorio de trabajo para leer `config.json` y guardar los volcados `dump_*.json`.

Para enviar señales, buscar el PID principal desde otra terminal:

```bash
pgrep -af 'python.*src/main.py'
```

Reemplazar `PID` por el número del proceso principal del monitor:

```bash
kill -HUP PID
kill -USR2 PID
kill -USR1 PID
```

También se puede ejecutar con Docker desde la raíz del repositorio:

```bash
docker compose --profile tp1 run --build --rm monitor
```

Este comando usa un contenedor temporal; los volcados que genere dentro de él se eliminan al salir. Para conservarlos directamente en esta carpeta, usar la ejecución con Python indicada arriba.

Los scripts de `ejemplos/` permiten consultar `stat` y `status` del proceso que los ejecuta:

```bash
python3 ejemplos/test_proc.py
python3 ejemplos/test_status.py
```
