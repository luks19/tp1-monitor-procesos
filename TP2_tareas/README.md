# TP2 — Plataforma de tareas distribuidas

Lucas Valdemoros · Computación II · 2026

API para recibir trabajos de espera, descarga de URLs y cálculo de hashes. Permite consultar su estado y resultado, cancelarlos y ver estadísticas. El estado se mantiene en memoria y se guarda en JSON al cerrar.

## Cómo ejecutarlo y probarlo

Desde la raíz del repositorio:

```bash
docker compose up --build
```

La API queda en `http://127.0.0.1:8000` y la documentación interactiva en `http://127.0.0.1:8000/docs`.

En otra terminal, crear una tarea de cada tipo:

```bash
curl -sS -X POST http://127.0.0.1:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"esperar","segundos":10,"timeout":20}'

curl -sS -X POST http://127.0.0.1:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"hashear","texto":"hola","iteraciones":2000000}'

curl -sS -X POST http://127.0.0.1:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"descargar","urls":["https://example.com","https://www.python.org"]}'
```

El POST devuelve un ID sin esperar que termine el trabajo. Reemplazar `ID` en las consultas:

```bash
curl -sS http://127.0.0.1:8000/tareas
curl -sS 'http://127.0.0.1:8000/tareas?estado=ejecutando'
curl -sS http://127.0.0.1:8000/tareas/ID
curl -sS -X DELETE http://127.0.0.1:8000/tareas/ID
curl -sS http://127.0.0.1:8000/estadisticas
```

Los estados son `pendiente`, `ejecutando`, `completada`, `fallida` y `cancelada`. Un pedido inválido devuelve 422; un ID inexistente, 404; cancelar una completada o fallida, 409. Cuando la cola está llena se responde 503 sin registrar el pedido. Repetir DELETE sobre una cancelada es válido.

El timeout predeterminado es de 30 segundos y empieza cuando un worker toma la tarea; no incluye la espera en cola. Se puede cambiar en cada pedido con `timeout`.

## Organización y decisiones

```text
Cliente HTTP → FastAPI → asyncio.Queue → workers corrutina
                  ↑                         ├─ esperar: asyncio.sleep
             estado y resultado             ├─ descargar: httpx async
                  ↑                         └─ hashear: pool de procesos
                  └───────────────────────────────────┘
                  └─ al cerrar: estado_<timestamp>.json
```

`app.py` contiene la API; `modelos.py`, la validación; `gestor.py`, la cola, los estados y el cierre; `tareas.py`, las descargas y los hashes. `mediciones.py` ejecuta los experimentos.

La cola es `asyncio.Queue` porque sus esperas no bloquean el event loop. `queue.Queue` está pensada para threads. Los workers consumen pedidos y llaman a `task_done()` al terminar cada entrada. Es el patrón productor-consumidor de las clases 11 y 21.

La API usa un único proceso. Los workers modifican el estado en ese mismo event loop y no suspenden entre comprobarlo y actualizarlo; por eso esas operaciones no necesitan un Lock. Los procesos de cálculo devuelven resultados, sin modificar ese estado. Esto retoma la separación de memoria vista en las clases 3, 8 y 9. No levantar Uvicorn con varios procesos de API: cada uno tendría su propio registro.

Para las descargas se reutiliza un `httpx.AsyncClient` y un semáforo limita las conexiones simultáneas entre todos los trabajos (clase 20). Cada URL devuelve código HTTP, bytes, tiempo y posible error. Un fallo en una URL no borra los resultados de las demás; se debe revisar `error` por URL.

El hash se calcula con SHA-256 iterado sobre el digest anterior. `ProcessPoolExecutor` evita hacer ese cálculo dentro del event loop y mantiene disponible la API (clases 9, 10 y 21). Se usa `spawn` y una función de módulo que se puede enviar al proceso.

Cancelar una corrutina no detiene una función que ya corre en otro proceso. Por eso el hash se divide en lotes: al cancelar se recoge el lote activo y no se envía otro. En las descargas, `TaskGroup` recoge las operaciones hijas y los contextos HTTP cierran las respuestas. Un timeout marca la tarea como fallida. La limpieza puede demorar la respuesta de cancelación o superar brevemente el timeout.

Un error de operación queda registrado y el worker sigue con otro pedido. Si una excepción escapa de ese manejo y termina al worker, se reduce la capacidad: no hay reinicio automático. Esta distinción está contemplada en la clase 21.

## Configuración y cierre

Por defecto hay cuatro workers, dos procesos de CPU, una cola de cien entradas y hasta veinte descargas simultáneas. Se pueden cambiar al iniciar:

```bash
TP2_WORKERS=2 TP2_PROCESOS=1 docker compose up --build
```

Compose también admite `TP2_CAPACIDAD`, `TP2_DESCARGAS`, `TP2_LOTE_HASH` (100000), `TP2_CIERRE` (3 segundos) y `TP2_PUERTO` (8000).

SIGINT/SIGTERM inician el cierre: se deja de aceptar trabajo, se espera hasta el plazo configurado, se cancela lo restante y se cierran los recursos. El estado se guarda en `TP2_tareas/estado/estado_<timestamp>.json`, mediante el volumen de Docker. Al arrancar se informa si hay un volcado anterior; no se restaura.

Para comprobarlo, crear una espera de 60 segundos y ejecutar `docker compose stop tareas`. Revisar el JSON y, al iniciar de nuevo, `docker compose logs tareas`. En una prueba con espera activa, la parada tardó 4,42 segundos: el plazo de tres segundos no incluye toda la limpieza.

## Pruebas y mediciones

Para ejecutar las pruebas fuera de Docker, desde la raíz con Python 3.11+:

```bash
python3 -m venv .venv
.venv/bin/pip install -r TP2_tareas/requirements-dev.txt
.venv/bin/python -m pytest -q
```

Las 27 pruebas cubren la API, cola llena, cancelación, timeouts, resultados reales, recuperación del worker y cierre con señales.

Mediciones del 17/10/2026, Python 3.12.3 en Linux/WSL2, cuatro workers y dos procesos. Son corridas locales individuales.

**Descargas.** Veinte pedidos HTTP a un servidor local con respuestas de 1024 bytes y demora de 0,1 segundos: secuencial, **2,223 s**; concurrente, **0,231 s**; mejora de **9,61 veces**. Completaron veinte en ambos casos. Se solapan las esperas; no se acelera cada respuesta. [Datos](resultados/io.json).

**CPU.** Con dos millones de iteraciones, el GET durante el cálculo tardó **1089,2 ms sin executor** y **3,38 ms con executor**. El experimento completo tardó 1,115 y 1,129 segundos respectivamente: la mejora fue poder responder durante el cálculo. La referencia bloqueante está aislada en el módulo de mediciones. [Datos](resultados/cpu.json).

**Pool.** Con hashes de 400000 iteraciones:

| Tareas | Tiempo total (s) | Tareas/s | Espera media en cola (s) |
| --- | --- | --- | --- |
| 2 | 0,386 | 5,18 | 0,001 |
| 4 | 0,819 | 4,88 | 0,001 |
| 8 | 1,116 | 7,17 | 0,262 |
| 16 | 2,227 | 7,19 | 0,786 |
| 32 | 4,424 | 7,23 | 1,891 |

Todas completaron. Desde ocho tareas, el rendimiento quedó cerca de 7,2 tareas/s y aumentó principalmente la cola. Los lotes pequeños muestran variación; esto no establece el máximo de cualquier equipo. [Datos con tiempos de ejecución y p95](resultados/pool.json).

Para repetir los experimentos después de instalar las dependencias:

```bash
.venv/bin/python -m TP2_tareas.mediciones io
.venv/bin/python -m TP2_tareas.mediciones cpu --iteraciones 2000000
.venv/bin/python -m TP2_tareas.mediciones pool --iteraciones 400000 --cantidades 2 4 8 16 32
```

## Límites

El historial permanece en memoria y crece; limitar la cola no limita los resultados guardados. La cancelación CPU espera al lote activo y no es instantánea. Cancelar una descarga solo cierra la operación local. Si vence el timeout del trabajo no se conservan resultados parciales. Las mediciones describen esta configuración y no garantizan capacidad de producción.

## Aprendizaje personal

Una de las cosas que me quedó más clara con este trabajo es la diferencia entre aceptar una tarea y ejecutarla. Que la API devuelva un identificador no significa que el trabajo haya terminado: puede seguir pendiente en la cola hasta que un worker esté disponible. También entendí mejor que el worker sigue funcionando después de terminar o cancelar una tarea y puede atender la siguiente.

Otro punto fue la cancelación. Antes podía pensar que mostrar el estado “cancelada” era suficiente, pero hay que comprobar qué pasó con la operación. No es lo mismo cancelar una tarea pendiente que una que ya empezó. Además, después de cancelarla, hay que verificar que el servicio pueda seguir procesando trabajos.

Esto se relaciona con la devolución de mi TP1: no alcanza con que una función esté escrita o que el README diga que funciona. Hay que comprobar su efecto real. Para este trabajo tomé esa corrección como criterio de revisión: mirar los estados, los resultados y el comportamiento posterior, en lugar de quedarme solamente con la respuesta de una operación.
