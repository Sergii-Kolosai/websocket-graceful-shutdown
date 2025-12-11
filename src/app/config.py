import os

APP_STATE_MANAGER: str = 'manager'
APP_STATE_REDIS: str = 'redis'

REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
REDIS_BROADCAST_CHANNEL: str = os.getenv('REDIS_BROADCAST_CHANNEL', 'ws:broadcast')
WS_CONNECTIONS_KEY: str = os.getenv('WS_CONNECTIONS_KEY', 'ws:connections')

REDIS_PUBSUB_POLL_INTERVAL: float = float(
    os.getenv('REDIS_PUBSUB_POLL_INTERVAL', '1.0')
)

GRACEFUL_SHUTDOWN_TIMEOUT: int = int(
    os.getenv('GRACEFUL_SHUTDOWN_TIMEOUT', '30') # 1800
)
GRACEFUL_SHUTDOWN_LOG_INTERVAL: int = int(
    os.getenv('GRACEFUL_SHUTDOWN_LOG_INTERVAL', '5')
)
