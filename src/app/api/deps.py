from fastapi import Depends, Request, WebSocket
from typing import Annotated
from redis.asyncio import Redis

from app.config import APP_STATE_MANAGER, APP_STATE_REDIS
from app.core import ConnectionManager


def _resolve_manager(app) -> ConnectionManager:
    """Low-level resolver: read manager from app.state."""
    manager: ConnectionManager | None = getattr(app.state, APP_STATE_MANAGER, None)
    if manager is None:
        raise RuntimeError('ConnectionManager is not initialized')
    return manager


def get_manager_http(request: Request) -> ConnectionManager:
    """Resolve ConnectionManager for HTTP endpoints."""
    return _resolve_manager(request.app)


def get_manager_ws(websocket: WebSocket) -> ConnectionManager:
    """Resolve ConnectionManager for WebSocket endpoints."""
    return _resolve_manager(websocket.app)


def get_redis(request: Request) -> Redis:
    """Resolve Redis client from application state."""
    redis: Redis | None = getattr(request.app.state, APP_STATE_REDIS, None)
    if redis is None:
        raise RuntimeError('Redis client is not initialized')
    return redis


ManagerHttpDep = Annotated[ConnectionManager, Depends(get_manager_http)]
ManagerWsDep = Annotated[ConnectionManager, Depends(get_manager_ws)]
RedisDep = Annotated[Redis, Depends(get_redis)]
