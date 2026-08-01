# TP1 — Monitor de Procesos y Threads

**Computación II — Universidad de Mendoza — 2026**

## Descripción

Monitor de procesos del sistema operativo Linux en tiempo real, similar a `htop`.
Lee `/proc` directamente (sin `psutil`) y muestra 7 vistas alternables:
resumen, memoria, file descriptors, threads, señales, scheduling y sistema global.

Arquitectura multiproceso: un recolector + 7 analizadores paralelos + Manager compartido + TUI con `rich`.

## Requisitos

- Docker y Docker Compose

## Cómo correr

    docker compose up --build

Para correr sin Docker (requiere Python 3.11+ y Linux):

    pip install rich
    python3 -m src.main

## Keybindings

| Tecla | Acción |
|-------|--------|
| 1-7 / r m f t s p g | Cambiar vista |
| Arriba / Abajo | Navegar procesos |
| c | Ciclar orden (PID / CPU% / RSS) |
| + / - | Ajustar intervalo de la vista activa |
| / | Filtrar por nombre |
| h / ? | Ayuda |
| q | Salir |

## Señales

    kill -SIGUSR1 <PID>   # dump del snapshot a dump_<timestamp>.json
    kill -SIGUSR2 <PID>   # toggle modo verbose
    kill -SIGHUP  <PID>   # recargar config.json

## Arquitectura

    main.py
    ├── Manager (snapshot compartido entre procesos)
    ├── 7 analizadores (procesos independientes, cada uno con su intervalo)
    │   ├── resumen.py    — CPU%, RSS, estado, threads  (cada 2s)
    │   ├── memoria.py    — segmentos, swap             (cada 3s)
    │   ├── fds.py        — file descriptors            (cada 5s)
    │   ├── threads.py    — LWPs por proceso            (cada 2s)
    │   ├── senales.py    — máscaras decodificadas      (cada 10s)
    │   ├── scheduling.py — nice, priority, ctx switches(cada 10s)
    │   └── sistema.py    — CPU global, memoria, load   (cada 2s)
    └── display.py        — TUI con rich (7 vistas alternables)

## Decisiones de diseño

**Por qué Manager.dict y no Value/Array**
Los datos de cada proceso son estructuras complejas (dicts anidados con strings y listas).
Value y Array solo soportan tipos primitivos de C. Manager.dict permite compartir
objetos Python arbitrarios entre procesos, a costa de mayor overhead por IPC.

**Por qué 7 procesos analizadores y no threads**
Cada analizador hace trabajo CPU-bound (parsear /proc para todos los procesos del sistema).
Con threads, el GIL de Python impediría la ejecución paralela real. Con procesos,
cada analizador tiene su propio intérprete y corre en un core distinto.

**Cómo se evitan race conditions**
El snapshot usa Manager.dict cuyas operaciones son serializadas por el proceso Manager.
Cada analizador escribe solo en su propia clave (snapshot resumen, snapshot memoria, etc.),
sin solapamiento con los demás analizadores.

**Manejo de señales**
Los handlers de señales solo setean flags (multiprocessing.Value con tipo b).
La lógica real (dump, reload) se ejecuta en el loop principal de la TUI,
no en el handler — esto garantiza que los handlers son async-signal-safe.

## Limitaciones conocidas

- El cálculo de CPU% requiere dos lecturas separadas; la primera lectura muestra 0%.
- Algunos procesos del kernel no tienen cmdline — se muestra el nombre entre corchetes.
- Procesos de otros usuarios pueden dar PermissionError al leer sus FDs.
- El intervalo de los analizadores se pasa al crearlos y no se actualiza dinámicamente.

## Autor

Lucas Valdemoros — Ingeniería en Informática — Universidad de Mendoza — 2026
