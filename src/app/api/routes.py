from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import ManagerHttpDep, RedisDep, ManagerWsDep
from app.config import REDIS_BROADCAST_CHANNEL
from app.core.logging import get_logger
from app.domain import BroadcastRequest


logger = get_logger(__name__)
router = APIRouter()

@router.get('/')
async def root(manager: ManagerHttpDep):
    """Return local and global WebSocket connection counts.

    Args:
        manager: Injected ConnectionManager instance.

    Returns:
        dict: Local and global connection statistics.
    """
    local = manager.local_active_count
    global_count = await manager.global_active_count()
    return {
        'status': "ok",
        'local_active_connections': local,
        'global_active_connections': global_count,
    }


@router.post('/broadcast')
async def broadcast(payload: BroadcastRequest, redis: RedisDep, manager: ManagerHttpDep):
    """Publish a global broadcast message via Redis Pub/Sub.

    Args:
        payload: Incoming broadcast request containing `.message`.
        redis: Injected Redis client.
        manager: Injected ConnectionManager instance.

    Returns:
        dict: Result flag and current global connection count.
    """

    await redis.publish(REDIS_BROADCAST_CHANNEL, payload.message)
    global_count = await manager.global_active_count()

    return {
        'published': True,
        'global_active_connections': global_count,
    }


@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket, manager: ManagerWsDep):
    """Handle a WebSocket connection and echo incoming messages.

    Args:
        websocket: The client WebSocket connection.

    Raises:
        WebSocketDisconnect: When the client disconnects.
    """
    if manager is None:
        await websocket.close(code=1011)
        logger.error('ConnectionManager is not initialized for WebSocket')
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f'echo: {data}')
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

    except (ConnectionResetError, BrokenPipeError):
        await manager.disconnect(websocket)

    except RuntimeError as exc:
        logger.warning(f'WebSocket runtime error: {exc}')
        await manager.disconnect(websocket)

@router.get('/health', tags=['health'])
async def health(manager: ManagerHttpDep, redis: RedisDep):
    """Health check endpoint for the service and its dependencies.

    Checks:
        - Redis availability via PING.
        - Global WebSocket connection count.

    Args:
        manager: Injected ConnectionManager instance.
        redis: Injected Redis client instance.

    Returns:
        dict: Overall status and per-component health information.
    """
    redis_ok = False
    try:
        pong = await redis.ping()
        redis_ok = bool(pong)
    except Exception as exc:
        logger.warning(f'Redis health check failed: {exc}')

    global_count = await manager.global_active_count()

    status = 'ok' if redis_ok else 'degraded'

    return {
        'status': status,
        'redis': {'ok': redis_ok},
        'websocket': {
            'global_active_connections': global_count,
        },
    }