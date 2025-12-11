# WebSocket Service with Graceful Shutdown

This project provides a WebSocket service built with **FastAPI**, **Uvicorn**, and **Redis**, supporting **multiple workers**, **connection tracking**, and a fully working **graceful shutdown** mechanism.

---

## 1. Setup Instructions

### Why Docker is used

Windows does **not** support running Uvicorn with multiple workers (`--workers N`) due to OS limitations in process forking.  
Because of this, **the multi-worker setup required by the task cannot be tested or executed on Windows natively**.

Docker solves this problem:

- it runs Linux inside a container;
- Uvicorn can spawn multiple workers normally;
- graceful shutdown works correctly (SIGTERM → shutdown lifecycle);
- Redis and the application run in a reproducible environment.

Therefore, **Docker is the only reliable way to run and test multi-worker WebSocket behavior on Windows**.

---

### 1.1 Run with Docker (recommended)

```bash
docker compose up --build
```

Services started:

- `app` — FastAPI + WebSocket server  
- `redis` — used for global connection tracking and Pub/Sub broadcasting  

Application will be available at:

- http://localhost:8000

---

### 1.2 Run locally without Docker

1. Start Redis:

```bash
docker run --rm -p 6379:6379 redis:7-alpine
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the application:

```bash
uvicorn app.app:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## 2. How to Test the WebSocket Endpoint

### 2.1 Connect via browser console

Open DevTools → Console and execute:

```js
let ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => console.log("connected");
ws.onmessage = (event) => console.log("received:", event.data);

// Optional:
ws.send("hello server");
```

Expected output:

```
connected
received: echo: hello server
```

---

### 2.2 Test broadcast

1. Open Swagger UI: http://localhost:8000/docs  
2. Open `POST /broadcast`  
3. Send:

```json
{ "message": "hello everyone" }
```

Each active WebSocket client (in any worker) will receive:

```
hello everyone
```

---

### 2.3 Check active connections

Send:

```
GET http://localhost:8000/
```

Example response:

```json
{
  "status": "ok",
  "local_active_connections": 1,
  "global_active_connections": 3
}
```

---

## 3. Explanation of Graceful Shutdown Logic

This service includes production-grade graceful shutdown with full multi-worker support.

---

### 3.1 How it works

1. Docker or Uvicorn sends **SIGTERM** to the application.
2. FastAPI enters the shutdown phase via the `lifespan` function.
3. Each worker:
   - stops accepting new WebSocket connections;
   - checks the **global** connection count in Redis;
   - waits until:
     - all clients disconnect, or
     - shutdown timeout expires.

---

### 3.2 Shutdown behavior (with logs)

Example logs during shutdown:

```
[worker=10] Shutdown initiated → waiting for global disconnect (timeout=30s)
[worker=10] Shutdown progress | global=2 | remaining=19s
[worker=10] All global WS connections closed → shutdown complete.
```

---

### 3.3 Forced shutdown

If clients remain connected after timeout:

```
FORCE shutdown → still 1 clients connected globally
```

---

### 3.4 Why Redis is needed

Multiple workers do not share memory — they are isolated OS processes.

Redis is used to coordinate them:

- stores connection IDs for all WebSocket clients globally  
- provides a Pub/Sub channel for broadcasting messages  
- allows every worker to:
  - know the **global** number of connections  
  - receive broadcast messages  
  - participate in coordinated graceful shutdown

As a result:

- broadcasting works across all workers  
- graceful shutdown waits for **all** clients globally  
- the whole system behaves like a single WebSocket server  


---

## 4. Architecture Overview

This project is structured as a small, modular, production-oriented WebSocket service.  
Below is the architecture overview, including components, project layout, and key design decisions.

---

### 4.1 High-Level Architecture

```
          ┌──────────────┐
          │   Browser     │
          │  WebSocket    │
          └──────┬───────┘
                 │ WS
                 ▼
        ┌──────────────────┐
        │   Uvicorn Worker │  (Worker A)
        │  in FastAPI app  │
        └──────┬───────────┘
               │ local connections
               │
               ▼
        ┌──────────────────────┐
        │  ConnectionManager   │
        │ - tracks WS clients  │
        │ - local broadcast    │
        └────────┬────────────┘
                 │ global conn IDs
                 ▼
           ┌───────────────┐
           │    Redis       │
           │ global state   │
           │ Pub/Sub channel│
           └─────┬─────────┘
                 │ broadcast events
                 ▼
        ┌──────────────────┐
        │   Uvicorn Worker │  (Worker B)
        │  in FastAPI app  │
        └──────────────────┘
```

Redis provides:

1. **Global WebSocket connection registry** (Redis Set)  
2. **Global broadcast system** (Redis Pub/Sub)

Each worker keeps **its own local list** of WebSocket clients.  
All workers subscribe to the same Redis Pub/Sub channel and react independently.

This architecture allows:

- horizontal scaling via Uvicorn workers;
- consistent global connection tracking;
- deterministic graceful shutdown across workers;
- stateless workers (only Redis holds shared state).

---

### 4.2 Project Structure

```
project_root/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── src/
    └── app/
        ├── main.py                  # FastAPI entrypoint + lifespan integration
        ├── config.py                # Application configuration (Redis, timeouts)
        ├── api/
        │   ├── routes.py            # HTTP + WebSocket endpoints
        │   └── deps.py              # Dependency injection helpers
        ├── core/
        │   ├── connection_manager.py# Local connection tracking per worker
        │   ├── lifecycle.py         # Startup + graceful shutdown logic
        │   └── logging.py           # Unified logging (through uvicorn.error)
        └── domain/
            └── broadcast.py         # Pydantic models for API requests
```

The project is intentionally separated into clear layers:

#### **`api/` — Transport Layer**
- Contains transport-level definitions: HTTP routes, WebSocket endpoints.
- Minimal logic; delegates everything to core components.

#### **`core/` — Business Logic**
- `ConnectionManager`: manages WebSocket connections, Redis, broadcasting.
- `lifecycle.py`: orchestrates startup and shutdown logic.
- `logging.py`: consistent per-module loggers.

#### **`domain/` — Models**
- Pydantic models shared across modules.
- Keeps validation separate from routing logic.

#### **`config.py` — Configuration**
- Only application-level config (Redis URL, shutdown timeouts, keys).
- Infrastructure-level config (host, port, workers) is in Dockerfile.

#### **Dockerfiles / Compose**
- Ensures a reproducible environment.
- Required to run multiple workers on Windows.

---

### 4.3 Key Design Decisions

#### **1. Using Redis instead of in-memory state**
Multiple workers do not share memory → all shared data must be external:

- connection IDs stored in Redis Set;
- broadcast messages via Pub/Sub.

This allows:

- correct multi-worker behavior,
- scalable architecture,
- clean and predictable graceful shutdown coordination.

---

#### **2. Using FastAPI lifespan instead of deprecated startup/shutdown handlers**

FastAPI deprecated `@app.on_event("startup")`.

We use:

```python
@asynccontextmanager
async def lifespan(app):
    lifespan_context = await setup_lifespan(app)
    try:
        yield
    finally:
        await shutdown_lifespan(lifespan_context)
```

Benefits:

- explicit resource allocation and cleanup
- unified flow for all workers
- no hidden globals or implicit state

---

#### **3. Using Docker for multi-worker support**

Uvicorn's multi-worker mode does **not work on Windows**.  
Docker provides a Linux environment, where:

- Uvicorn workers fork correctly,
- SIGTERM is delivered properly,
- graceful shutdown runs as intended.

This ensures the system behaves the same as in production.

---

#### **4. Unified logging system**

All logs use:

```python
logger = get_logger(__name__)
```

Which is a child of `uvicorn.error`.  
This ensures:

- the same formatting,
- single output stream,
- no duplicated handlers,
- clean visibility inside Docker logs.

Logs include:

- WebSocket connect/disconnect events,
- broadcast actions,
- Redis listener lifecycle,
- shutdown progress,
- health degradation.

---

### 4.4 Graceful Shutdown Architecture

At shutdown:

1. Docker sends **SIGTERM**.
2. Uvicorn stops accepting new requests.
3. Lifespan shutdown starts.
4. Each worker:
   - polls Redis for global WS connection count,
   - logs progress,
   - waits until count reaches **0** or timeout expires.
5. Redis Pub/Sub listener stops.
6. Redis connection closes.
7. Worker exits cleanly.

This guarantees that:

- no worker kills active connections abruptly,
- all clients receive proper disconnect,
- system shuts down consistently across all workers.

---
