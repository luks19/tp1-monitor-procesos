# TP2 — Plataforma de tareas distribuidas

Lucas Valdemoros · Computación II · Universidad de Mendoza · 2026

Servicio HTTP para encolar, consultar y cancelar descargas, hashes y esperas.
Implementa la [consigna de la cátedra](https://github.com/Catedra-de-Computacion-II/compu2_um_2026/blob/main/trabajos_practicos/TP2_tareas/consigna.md) con estado en memoria, workers corrutina y un executor de procesos para CPU.

## Ejecución

Desde la raíz del repositorio:

```bash
docker compose up --build
```

API: `http://127.0.0.1:8000`. Documentación interactiva: `http://127.0.0.1:8000/docs`.
El servicio se llama `tareas`. No requiere una base de datos ni servicios adicionales.

En otra terminal:

```bash
curl -sS -X POST http://127.0.0.1:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"esperar","segundos":10,"timeout":20}'

curl -sS -X POST http://127.0.0.1:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"hashear","texto":"hola","iteraciones":2000000,"timeout":30}'

curl -sS -X POST http://127.0.0.1:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"descargar","urls":["https://example.com","https://www.python.org"],"timeout":30}'

curl -sS http://127.0.0.1:8000/tareas
curl -sS 'http://127.0.0.1:8000/tareas?estado=ejecutando'
curl -sS http://127.0.0.1:8000/estadisticas
```

Cada POST devuelve 201 con un `id`, inicialmente `pendiente`, sin esperar la operación. Copiar ese ID para consultar o cancelar:

```bash
curl -sS http://127.0.0.1:8000/tareas/ID
curl -sS -X DELETE http://127.0.0.1:8000/tareas/ID
```

DELETE devuelve el registro una vez recogida la cancelación; repetirlo sobre una tarea cancelada es válido. Una completada o fallida devuelve 409 y conserva su resultado. IDs inexistentes: 404. Pedido inválido: 422. Cola llena o servidor cerrando: 503 sin registrar una tarea fantasma.

`timeout` es opcional, predeterminado 30 s, y limita la ejecución desde que la toma un worker; no incluye la espera en cola. Debe ser positivo y no superar 3600 s. Cada petición HTTP de descarga tiene además timeout de 10 s para sus operaciones de red.

## Arquitectura

```text
                        un proceso Uvicorn / un event loop
 cliente HTTP ──> FastAPI ──> asyncio.Queue limitada ──> N workers corrutina
                    │                                     │
                    │                                     ├─ esperar: asyncio.sleep
                    │                                     ├─ descargar: httpx async
                    │                                     │   + semáforo compartido
                    │                                     └─ hashear: run_in_executor
                    │                                              │
                    └──── registros en memoria <──────────── pool de procesos
                              │                              (devuelve el digest)
                              └─ cierre ──> estado_<timestamp>.json
```

| Archivo | Responsabilidad |
| --- | --- |
| `app.py` | Validación HTTP, endpoints y lifespan. |
| `modelos.py` | Pedidos por tipo y configuración validada. |
| `gestor.py` | Cola, workers, estados, estadísticas y cierre. |
| `tareas.py` | Descargas y cálculo por lotes fuera del loop. |
| `mediciones.py` | Experimentos separados del servicio habitual. |

## Decisiones y relación con las clases

**Cola y workers — clases 11 y 21.** `asyncio.Queue` suspende corrutinas sin bloquear el hilo. `queue.Queue` está pensada para threads y sus esperas bloquearían el loop. La cola FIFO desacopla recepción y ejecución. Su capacidad limita las entradas pendientes; cuando se llena, `put_nowait` permite rechazar inmediatamente. Cada entrada recibida tiene un `task_done()` en `finally`.

Los workers permanentes se crean una vez en lifespan y se conservan sus referencias. Cada uno espera una Task hija que representa el trabajo actual. Cancelar ese trabajo no debe eliminar al worker. Una excepción de operación marca la tarea como fallida, registra el error y permite atender la siguiente. Una excepción no capturada fuera de ese manejo terminaría al worker y reduciría la capacidad; no se implementó un supervisor de reinicios.

**Dueño del estado — clases 3, 8, 9, 16 y 19.** Los procesos no comparten un diccionario común por defecto. Por eso Uvicorn usa un único proceso de API: el estado se modifica en su event loop y los procesos de CPU devuelven datos. Las actualizaciones de estado no suspenden en medio de una comprobación y escritura. No se introdujeron locks ni un Manager porque no hay escritores externos a ese loop. No ejecutar esta aplicación con `uvicorn --workers 4`: serían cuatro registros independientes.

**Descargas — clases 12, 13 y 20.** Un `httpx.AsyncClient` reutilizado evita crear otro pool de conexiones por URL. La lectura se hace por bloques para contar bytes sin retener todo el cuerpo. Un semáforo compartido por todos los trabajos limita las descargas simultáneas. Sus tiempos por URL comienzan al adquirir ese permiso e incluyen la conexión y lectura, pero no la espera del semáforo.

Cada URL devuelve `url`, `estado_http`, `bytes`, `segundos` y `error`. Un 404/503 es una respuesta HTTP y se conserva como tal. Un fallo de transporte se registra en esa URL, conservando los resultados de las otras; por eso el lote puede estar `completada` aunque una URL tenga `error`. Un timeout del trabajo completo, en cambio, lo deja `fallida`. TaskGroup recoge las descargas hijas si ocurre un fallo inesperado o se cancela el conjunto.

**CPU — clases 9, 10, 18 y 21.** Escribir `async def` no convierte SHA-256 iterado en una operación cooperativa. Se envía a `ProcessPoolExecutor` con funciones serializables a nivel de módulo. El pool se reutiliza. Se eligió `spawn` explícitamente para no depender del arranque predeterminado del sistema ni heredar conexiones del servidor.

El texto se codifica en UTF-8 y cada iteración calcula `sha256(dato).digest()`; el digest binario alimenta la siguiente. Solo el resultado final se convierte a hexadecimal. Se validan entre 1 y 100 millones de iteraciones, texto no vacío de hasta 100.000 caracteres y entre 1 y 100 URLs HTTP/HTTPS por trabajo.

**Cancelación — clases 6, 20 y 21.** `cancel()` solicita una excepción en un punto de suspensión, no mata arbitrariamente el trabajo. Para I/O se propaga la cancelación y se recoge la limpieza. En CPU, cancelar el Future no detiene una función que ya corre: por eso se envían lotes de hasta 100.000 iteraciones. `shield` conserva el Future del lote activo y el código espera su finalización antes de propagar la cancelación; no envía otro lote.

Esta adaptación permite reutilizar el pool sin dejar un hash largo abandonado. Agrega viajes de serialización: el lote no debe ser tan pequeño que domine ese costo ni tan grande que vuelva lenta la cancelación. Un timeout puede exceder brevemente el plazo mientras se recoge el lote activo, incluido su arranque si el proceso aún no estaba listo.

**Apagado — clases 2, 4, 6, 20 y 21.** Uvicorn recibe SIGINT/SIGTERM y ejecuta la salida de lifespan. El gestor deja de aceptar, da un plazo común al trabajo aceptado y, si vence, cancela lo restante. Se recogen workers mediante un centinela por worker, cliente HTTP y executor. Después se escribe un archivo temporal y se renombra a JSON. El directorio `TP2_tareas/estado/` está montado en `/datos`, para conservarlo al reemplazar el contenedor.

Al iniciar se informa por log si existe un volcado anterior; no se restaura, tal como permite la consigna. El plazo configurado corresponde a la espera del trabajo; el cierre completo incluye además limpieza, volcado y cierre de procesos. En la comprobación Docker, detener con una espera activa tardó 5,06 s con `TP2_CIERRE=3`. Compose concede 75 s, por encima del máximo configurable de 60 s más la limpieza normal.

## Configuración

Variables de entorno de arranque, también declaradas en Compose:

| Variable | Predeterminado | Límite |
| --- | --- | --- |
| `TP2_WORKERS` | 4 | 1–64 corrutinas |
| `TP2_PROCESOS` | 2 | 1–32 procesos |
| `TP2_CAPACIDAD` | 100 | 1–10.000 entradas pendientes |
| `TP2_DESCARGAS` | 20 | 1–100 simultáneas globales |
| `TP2_LOTE_HASH` | 100000 | 1.000–1.000.000 iteraciones |
| `TP2_CIERRE` | 3 | >0 y hasta 60 s |
| `TP2_PUERTO` | 8000 | Puerto publicado por Compose |

Ejemplo: `TP2_WORKERS=2 TP2_PROCESOS=1 docker compose up --build`.
En ejecución sin Docker, `TP2_DIRECTORIO` cambia la ubicación de los volcados.

Las estadísticas cuentan los cinco estados. `promedio_ejecucion` incluye todas las tareas terminadas que empezaron, aun fallidas o canceladas. `promedio_espera_cola` incluye todas las tareas que empezaron, incluso las activas. La ejecución incluye las esperas internas por semáforo o executor. `entradas_en_cola` puede incluir tareas canceladas pendientes de ser retiradas por un worker.

## Pruebas

Desde la raíz, con Python 3.11+ (la ejecución comprobada usa Python 3.12):

```bash
python3 -m venv .venv
.venv/bin/pip install -r TP2_tareas/requirements-dev.txt
.venv/bin/python -m pytest -q
```

Las pruebas usan HTTP local, procesos reales, SIGINT y SIGTERM. Cubren respuesta inmediata, datos inválidos, cola llena sin registros fantasma, cancelación pendiente/activa, cancelación antes de empezar el cuerpo, timeouts, conservación de capacidad, resultado SHA-256 conocido, resultados por URL y JSON de cierre. También ejecutan los tres experimentos con cargas pequeñas.

Prueba manual del apagado: crear una espera de 60 s, ejecutar `docker compose stop tareas` y abrir el nuevo `TP2_tareas/estado/estado_*.json`. Al levantar de nuevo, comprobar el mensaje de volcado previo en `docker compose logs tareas`. SIGKILL no ofrece apagado ordenado y no forma parte de esta garantía.

## Mediciones propias

Resultados del 17/10/2026, Python 3.12.3, Linux/WSL2, 16 CPU lógicas visibles, cuatro workers corrutina y dos procesos de CPU. Son mediciones locales de desarrollo, no resultados docentes ni una promesa de capacidad de producción. Los JSON conservan valores sin redondear y las condiciones.

### 1. Veinte descargas HTTP

Servidor HTTP local independiente de la API, 1024 bytes por respuesta y demora controlada de 0,1 s. Las descargas son peticiones HTTP reales; la espera está en el servidor, no sustituye la descarga del cliente. Se comparó el mismo recurso veinte veces con httpx secuencial y con nuestra tarea `descargar`, con límite global 20.

| Forma | Tiempo total | Exitosas |
| --- | --- | --- |
| Secuencial | 2,223 s | 20/20 |
| Concurrente | 0,231 s | 20/20 |

Speedup: **9,61×**. Las esperas se solapan; no llega a 20× porque también hay conexiones, planificación, HTTP, encolado y consulta del resultado. [Datos completos](resultados/io.json).

### 2. API durante cálculo CPU

Dos millones de iteraciones SHA-256. Una API de referencia mínima, aislada en `mediciones.py`, ejecuta deliberadamente el cálculo dentro del loop; la API habitual lo envía al executor. El cliente corre en otro proceso y mide `GET /tareas` tras enviar el trabajo, con una pausa de 20 ms. Se realiza calentamiento antes de medir.

| Forma | GET durante cálculo | Tiempo total del experimento |
| --- | --- | --- |
| Sin executor | 1.089,2 ms | 1,115 s |
| Con executor | 3,38 ms | 1,129 s |

La mejora es la disponibilidad de la API, no una reducción del cálculo. La referencia bloqueante no tiene la cola y toda la instrumentación del servicio: compara el efecto de bloquear el loop, no el costo exacto de cada componente. El modo incorrecto no se puede activar en la aplicación normal. [Datos completos](resultados/cpu.json).

### 3. Saturación del pool

Se envían lotes crecientes de hashes de 400.000 iteraciones. El cliente lanza los POST concurrentemente y registra también fallos. Los procesos se calientan antes del primer lote. La latencia suma espera en cola y ejecución; p95 se calcula por rango más cercano. [Datos completos](resultados/pool.json).

| Tareas | Tiempo total (s) | Tareas/s | Cola media (s) | Ejecución media (s) | Latencia p95 (s) |
| --- | --- | --- | --- | --- | --- |
| 2 | 0,386 | 5,18 | 0,001 | 0,368 | 0,369 |
| 4 | 0,819 | 4,88 | 0,001 | 0,732 | 0,795 |
| 8 | 1,116 | 7,17 | 0,262 | 0,527 | 1,062 |
| 16 | 2,227 | 7,19 | 0,786 | 0,541 | 2,180 |
| 32 | 4,424 | 7,23 | 1,891 | 0,542 | 4,289 |

Todas las tareas completaron sin fallos. Con cuatro workers y dos procesos, el rendimiento se estabilizó alrededor de 7,2 tareas/s a partir de ocho tareas; aumentar el lote incrementó principalmente la espera en cola. Los lotes pequeños muestran variación y no una progresión uniforme. Son corridas individuales de esta configuración, no una estimación del máximo del equipo ni un estudio estadístico.

Comandos para reproducir los tres experimentos desde la raíz:

```bash
.venv/bin/python -m TP2_tareas.mediciones io --salida TP2_tareas/resultados/io.json
.venv/bin/python -m TP2_tareas.mediciones cpu --iteraciones 2000000 --salida TP2_tareas/resultados/cpu.json
.venv/bin/python -m TP2_tareas.mediciones pool --iteraciones 400000 --cantidades 2 4 8 16 32 --salida TP2_tareas/resultados/pool.json
```

Cada comando levanta sus servidores en puertos locales libres y los cierra. No requiere tener el contenedor levantado. Ejecutarlos por separado evita que compitan entre sí por CPU. No se deben reintentar los POST silenciosamente: un timeout de respuesta no prueba que la creación no haya ocurrido (clases 15 y 19).

## Limitaciones conocidas

- El historial completo permanece en memoria y crece; la capacidad de la cola no limita los resultados retenidos. No hay restauración, DB ni distribución entre varias máquinas.
- Un worker ocupado en CPU cuenta como ocupado aun si está esperando un proceso del executor. Las estadísticas distinguen la cola de aplicación, pero no instrumentan cada espera interna del executor.
- La cancelación CPU debe recoger el lote activo; su demora depende de la máquina, carga y arranque del proceso. No es una interrupción forzosa instantánea.
- Cancelar una descarga cierra la operación local; no obliga al servidor remoto a dejar de trabajar.
- Una URL con error no invalida otras descargas; revisar `error` por URL. No se conservan resultados parciales del lote si vence el timeout global.
- No hay reintentos automáticos, autenticación, prioridades, WebSockets ni supervisión de procesos ante fallos catastróficos. La API queda publicada solo en loopback del host.
- Los experimentos son corridas locales, con cliente y generador de carga propios; no prueban todos los tamaños de respuesta, máquinas o patrones de llegada.

## Aprendizaje personal

Una de las cosas que me quedó más clara con este trabajo es la diferencia entre aceptar una tarea y ejecutarla. Que la API devuelva un identificador no significa que el trabajo haya terminado: puede seguir pendiente en la cola hasta que un worker esté disponible. También entendí mejor que el worker sigue funcionando después de terminar o cancelar una tarea y puede atender la siguiente.

Otro punto fue la cancelación. Antes podía pensar que mostrar el estado “cancelada” era suficiente, pero hay que comprobar qué pasó con la operación. No es lo mismo cancelar una tarea pendiente que una que ya empezó. Además, después de cancelarla, hay que verificar que el servicio pueda seguir procesando trabajos.

Esto se relaciona con la devolución de mi TP1: no alcanza con que una función esté escrita o que el README diga que funciona. Hay que comprobar su efecto real. Para este trabajo tomé esa corrección como criterio de revisión: mirar los estados, los resultados y el comportamiento posterior, en lugar de quedarme solamente con la respuesta de una operación.
