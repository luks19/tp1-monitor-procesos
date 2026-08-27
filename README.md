# Monitor de Procesos y Threads en Linux

Monitor de procesos y threads del sistema operativo Linux en tiempo real implementado en Python 3 sobre arquitectura multiproceso POSIX, sin dependencias de bibliotecas de terceros para la extracción de métricas del kernel (`/proc`).

---

## Arquitectura del Sistema

El sistema implementa un modelo concurrente desacoplado basado en procesos independientes:

- **Analizadores Paralelos:** Siete procesos independientes (`multiprocessing.Process`) recolectan información específica desde `/proc` (`resumen`, `memoria`, `fds`, `senales`, `threads`, `scheduling`, `sistema`). Cada worker relista dinámicamente los PIDs en cada ciclo y duerme a su propio ritmo.
- **Memoria Compartida y Sincronización:**
  - Los intervalos de muestreo se gestionan mediante escalares compartidos en memoria (`multiprocessing.Value('d', ...)`), permitiendo la actualización dinámica y atómica desde la TUI o ante señales del sistema.
  - Las señales asíncronas se propagan mediante banderas compartidas (`multiprocessing.Value('b', ...)`).
  - Los datos analizados se centralizan en un diccionario administrado por `multiprocessing.Manager`.
  - La terminación limpia y coordinada se realiza mediante un `multiprocessing.Event` (`stop_event`).
- **Interfaz de Usuario (TUI):** Renderizado en terminal con `rich` utilizando entrada no bloqueante por `/dev/tty` con `termios` en modo cbreak.

---

## Vistas Disponibles

1. **Resumen (`resumen`):** Métricas principales de procesos (PID, USER, PR, NI, RES, S, %CPU calculado dinámicamente con `SC_CLK_TCK`, POLICY, MINFLT, MAJFLT, COMMAND).
2. **Memoria (`memoria`):** Segmentación y tamaño real de memoria virtual (`VmSize`, `VmRSS`, `VmHWM`, heap, stack, `.so`, ejecutables y total en KB).
3. **Descriptores de Archivos (`fds`):** Cantidad de FDs y resolución de enlaces simbólicos (`fd -> target`).
4. **Señales (`senales`):** Decodificación de máscaras POSIX de señales bloqueadas (`SigBlk`), ignoradas (`SigIgn`) y con manejador (`SigCgt`).
5. **Threads (`threads`):** Conteo de hilos por proceso, estado, prioridad y nivel nice.
6. **Scheduling (`scheduling`):** Políticas de planificación del kernel (OTHER, FIFO, RR, BATCH, IDLE, DEADLINE), prioridades de tiempo real y afinidad de CPUs (`Cpus_allowed_list`).
7. **Sistema (`sistema`):** Métricas globales del host (uptime, memoria total, libre, disponible y distribución de estados de procesos).

---

## Controles e Interacción (Keybindings)

| Tecla | Acción |
| :--- | :--- |
| `1` - `7` / `c` | Cambiar entre vistas activas |
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

- **`SIGHUP` (`kill -HUP <PID>`):** Relee `config.json` y actualiza inmediatamente los objetos de memoria compartida (`multiprocessing.Value`) de cada analizador activo respetando los umbrales mínimos.
- **`SIGUSR1` (`kill -USR1 <PID>`):** Genera un volcado completo de la instantánea actual del sistema en formato JSON (`dump_<timestamp>.json`).
- **`SIGUSR2` (`kill -USR2 <PID>`):** Alterna el modo *verbose* en pantalla, expandiendo la visualización de descriptores de archivos (de 3 a 20 FDs visibles).
- **`SIGTERM` / `SIGINT`:** Despierta a los analizadores mediante `stop_event`, espera su terminación (`join`) y cierra el `Manager` sin dejar procesos huérfanos.

---

## Restricciones de Intervalos Mínimos

Para evitar sobrecarga innecesaria sobre `/proc`, se aplican los siguientes límites mínimos de muestreo:

- `resumen`: 0.5s
- `threads`: 0.5s
- `memoria`: 1.0s
- `sistema`: 1.0s
- `fds`: 2.0s
- `senales`: 5.0s
- `scheduling`: 5.0s

---

## Ejecución

```bash
# Iniciar monitor
python3 src/main.py

# Enviar señales desde otra terminal
kill -HUP $(pgrep -f "src/main.py")
kill -USR2 $(pgrep -f "src/main.py")
kill -USR1 $(pgrep -f "src/main.py")