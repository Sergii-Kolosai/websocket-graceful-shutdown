import os
from typing import Dict, List
from uuid import uuid4

from fastapi import WebSocket
from redis.asyncio import Redis
from starlette.websockets import WebSocketDisconnect

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for a single worker process.

    Keeps track of:
    - local WebSocket connections in this worker;
    - a global registry of connections in Redis;
    - local and global active connection counts.
    """

    def __init__(self, redis: Redis, redis_set_key: str) -> None:
        """Initialize the connection manager.

        Args:
            redis: Redis client used for the global connection registry.
            redis_set_key: Redis set key used to track active connections.
        """
        self._redis = redis
        self._redis_set_key = redis_set_key

        self._connections: List[WebSocket] = []
        self._ws_to_id: Dict[WebSocket, str] = {}

        self.worker_id = os.getpid()

    @property
    def local_active_count(self) -> int:
        """Return the number of active WebSocket connections in this worker."""
        return len(self._connections)

    async def global_active_count(self) -> int:
        """Return the number of active WebSocket connections across all workers.

        Returns:
            int: Global number of active connections stored in Redis.
        """
        return int(await self._redis.scard(self._redis_set_key))

    async def connect(self, websocket: WebSocket) -> None:
        """Register a new WebSocket connection.

        The connection is:
        - accepted on the WebSocket level;
        - stored in local in-memory structures;
        - added to the global Redis set.

        Args:
            websocket: WebSocket connection to register.
        """
        await websocket.accept()

        conn_id = f'{self.worker_id}:{uuid4()}'
        self._connections.append(websocket)
        self._ws_to_id[websocket] = conn_id

        await self._redis.sadd(self._redis_set_key, conn_id)

        global_count = await self.global_active_count()
        logger.info(
            f'[worker={self.worker_id}] WS connected | '
            f'local={self.local_active_count} | global={global_count}'
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection.

        The connection is:
        - removed from local in-memory structures;
        - removed from the global Redis set (if it was registered).

        Args:
            websocket: WebSocket connection to unregister.
        """
        conn_id = self._ws_to_id.pop(websocket, None)

        if websocket in self._connections:
            self._connections.remove(websocket)

        if conn_id:
            await self._redis.srem(self._redis_set_key, conn_id)

        global_count = await self.global_active_count()
        logger.info(
            f'[worker={self.worker_id}] WS disconnected | '
            f'local={self.local_active_count} | global={global_count}'
        )

    async def broadcast_local(self, message: str) -> None:
        """Broadcast a message to all local WebSocket connections.

        Args:
            message: Text message to send to all local clients.
        """
        logger.info(
            f"[worker={self.worker_id}] Local broadcast '{message}' "
            f'→ {self.local_active_count} local connections'
        )

        for ws in list(self._connections):
            try:
                await ws.send_text(message)

            except WebSocketDisconnect:
                await self.disconnect(ws)

            except (ConnectionResetError, BrokenPipeError):
                await self.disconnect(ws)

            except RuntimeError as exc:
                logger.warning(
                    f'[worker={self.worker_id}] RuntimeError when sending → removing. {exc}'
                )
                await self.disconnect(ws)
