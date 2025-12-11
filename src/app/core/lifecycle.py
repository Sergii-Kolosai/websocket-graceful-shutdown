import asyncio
import datetime as dt
from dataclasses import dataclass

from fastapi import FastAPI
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.config import (
    REDIS_URL,
    REDIS_BROADCAST_CHANNEL,
    GRACEFUL_SHUTDOWN_TIMEOUT,
    GRACEFUL_SHUTDOWN_LOG_INTERVAL,
    WS_CONNECTIONS_KEY,
    APP_STATE_MANAGER,
    APP_STATE_REDIS,
    REDIS_PUBSUB_POLL_INTERVAL,
)
from app.core import ConnectionManager
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LifespanContext:
    """Container for resources managed during application lifespan.

    Attributes:
        redis: Redis client used for global state and Pub/Sub.
        manager: Connection manager for WebSocket connections.
        pubsub: Redis Pub/Sub client subscribed to the broadcast channel.
        stop_event: Event used to stop the Pub/Sub listener loop.
        listener_task: Background task running the Pub/Sub listener.
    """
    redis: Redis
    manager: ConnectionManager
    pubsub: PubSub
    stop_event: asyncio.Event
    listener_task: asyncio.Task


async def setup_lifespan(app: FastAPI) -> LifespanContext:
    """Initialize resources required for the application lifespan.

    This includes:
    - connecting to Redis;
    - clearing the global WebSocket connections key;
    - creating the ConnectionManager;
    - subscribing to the Redis Pub/Sub channel;
    - starting the background Pub/Sub listener task.

    Args:
        app: FastAPI application instance.

    Returns:
        LifespanContext: Initialized context with all runtime resources.
    """
    logger.info(f'Connecting to Redis at {REDIS_URL}')
    redis = Redis.from_url(REDIS_URL, decode_responses=True)

    # Remove stale connection records from previous runs.
    await redis.delete(WS_CONNECTIONS_KEY)

    manager = ConnectionManager(redis, redis_set_key=WS_CONNECTIONS_KEY)
    setattr(app.state, APP_STATE_REDIS, redis)
    setattr(app.state, APP_STATE_MANAGER, manager)

    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_BROADCAST_CHANNEL)

    stop_event = asyncio.Event()
    listener_task = asyncio.create_task(
        _broadcast_listener(pubsub, manager, stop_event)
    )

    logger.info('Application startup complete.')
    return LifespanContext(
        redis=redis,
        manager=manager,
        pubsub=pubsub,
        stop_event=stop_event,
        listener_task=listener_task,
    )


async def shutdown_lifespan(lifespan_context: LifespanContext) -> None:
    """Gracefully shut down resources created during startup.

    Steps:
    - wait until global WebSocket connection count reaches zero or
      a timeout is exceeded;
    - signal the Pub/Sub listener to stop;
    - wait for the listener task to finish;
    - close Pub/Sub and Redis connections.

    Args:
        lifespan_context: LifespanContext with initialized resources.
    """
    await _wait_for_global_shutdown(lifespan_context.manager)

    lifespan_context.stop_event.set()
    await lifespan_context.listener_task
    await lifespan_context.pubsub.close()
    await lifespan_context.redis.close()

    logger.info('Application shutdown complete.')


async def _broadcast_listener(
    pubsub: PubSub,
    manager: ConnectionManager,
    stop_event: asyncio.Event,
) -> None:
    """Background listener for Redis Pub/Sub broadcast messages.

    Reads messages from the configured Redis channel and forwards each
    message to all local WebSocket connections via the ConnectionManager.

    Args:
        pubsub: Redis Pub/Sub client subscribed to the broadcast channel.
        manager: ConnectionManager used to broadcast messages locally.
        stop_event: Event that signals the listener to stop.
    """
    logger.info(
        "Started Redis Pub/Sub listener on channel '%s'",
        REDIS_BROADCAST_CHANNEL,
    )

    while not stop_event.is_set():
        msg = await pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=REDIS_PUBSUB_POLL_INTERVAL,
        )
        if msg is None:
            continue

        data = msg["data"]
        await manager.broadcast_local(str(data))

    logger.info('Stopping Redis Pub/Sub listener...')


async def _wait_for_global_shutdown(manager: ConnectionManager) -> None:
    """Wait until all global WebSocket connections are closed or timeout expires.

    Args:
        manager: ConnectionManager providing global connection statistics.
    """
    start = dt.datetime.now()
    deadline = start + dt.timedelta(seconds=GRACEFUL_SHUTDOWN_TIMEOUT)

    logger.info(
        f'[worker={manager.worker_id}] Shutdown initiated → waiting for global '
        f'disconnect (timeout={GRACEFUL_SHUTDOWN_TIMEOUT}s)'
    )

    while True:
        global_count = await manager.global_active_count()
        now = dt.datetime.now()

        if global_count == 0:
            logger.info(
                f'[worker={manager.worker_id}] All global WS connections closed '
                f'→ shutdown complete.'
            )
            break

        if now >= deadline:
            logger.warning(
                f'[worker={manager.worker_id}] FORCE shutdown → still '
                f'{global_count} clients connected globally'
            )
            break

        remaining = int((deadline - now).total_seconds())
        logger.info(
            f'[worker={manager.worker_id}] Shutdown progress | '
            f'global={global_count} | remaining={remaining}s'
        )

        await asyncio.sleep(GRACEFUL_SHUTDOWN_LOG_INTERVAL)
