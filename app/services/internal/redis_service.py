# app/services/internal/redis_service.py

import logging
from typing import Optional
from redis.asyncio import Redis
from app.core.config import settings

# --- Module-level client ---
redis_client: Optional[Redis] = None
logger = logging.getLogger(__name__)


async def init_client():
    """Initializes the async Redis client."""
    global redis_client
    try:
        redis_url = settings.REDIS_URL
        logger.info(f"Connecting to Redis at: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")

        redis_client = Redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
        )
        # Test connection
        await redis_client.ping()
        logger.info("Successfully connected to Redis.")
    except Exception as e:
        logger.warning(
            f"Could not initialize Redis client. Error: {e}. "
            "Redis features will be disabled."
        )
        redis_client = None


async def close_client():
    """Closes the Redis client connection."""
    global redis_client
    if redis_client:
        await redis_client.aclose()
        logger.info("Redis connection closed.")


# --- Cache Operations ---


async def get(key: str) -> Optional[str]:
    """Get a value from Redis cache."""
    if not redis_client:
        return None
    try:
        return await redis_client.get(key)
    except Exception as e:
        logger.error(f"Redis GET error for key '{key}': {e}")
        return None


async def set(
    key: str,
    value: str,
    expire_seconds: Optional[int] = None
) -> bool:
    """
    Set a value in Redis cache.
    
    Args:
        key: The cache key
        value: The value to store
        expire_seconds: Optional TTL in seconds
    
    Returns:
        True if successful, False otherwise
    """
    if not redis_client:
        return False
    try:
        if expire_seconds:
            await redis_client.setex(key, expire_seconds, value)
        else:
            await redis_client.set(key, value)
        return True
    except Exception as e:
        logger.error(f"Redis SET error for key '{key}': {e}")
        return False


async def delete(key: str) -> bool:
    """Delete a key from Redis."""
    if not redis_client:
        return False
    try:
        await redis_client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Redis DELETE error for key '{key}': {e}")
        return False


async def exists(key: str) -> bool:
    """Check if a key exists in Redis."""
    if not redis_client:
        return False
    try:
        return await redis_client.exists(key) > 0
    except Exception as e:
        logger.error(f"Redis EXISTS error for key '{key}': {e}")
        return False


# --- Rate Limiting ---


async def increment_with_ttl(key: str, ttl_seconds: int) -> int:
    """
    Increment a counter and set TTL if it's a new key.
    Useful for rate limiting.
    
    Returns:
        The new count value, or 0 if Redis is unavailable
    """
    if not redis_client:
        return 0
    try:
        pipe = redis_client.pipeline()
        await pipe.incr(key)
        await pipe.expire(key, ttl_seconds)
        results = await pipe.execute()
        return results[0]
    except Exception as e:
        logger.error(f"Redis INCR error for key '{key}': {e}")
        return 0


# --- Session/Token Management ---


async def store_token(
    token_key: str,
    user_id: str,
    expire_seconds: int = 3600
) -> bool:
    """
    Store a token in Redis with expiration.
    Useful for temporary tokens, sessions, or OTP.
    """
    return await set(token_key, user_id, expire_seconds)


async def get_token(token_key: str) -> Optional[str]:
    """Retrieve a token from Redis."""
    return await get(token_key)


async def invalidate_token(token_key: str) -> bool:
    """Remove a token from Redis (logout/invalidation)."""
    return await delete(token_key)


# --- OAuth State Management ---


async def store_oauth_state(
    state: str,
    data: str,
    expire_seconds: int = 600  # 10 minutes
) -> bool:
    """
    Store OAuth state data temporarily.
    
    Args:
        state: The OAuth state parameter
        data: Data to store (e.g., code_verifier)
        expire_seconds: TTL for the state
    """
    key = f"oauth:state:{state}"
    return await set(key, data, expire_seconds)


async def get_oauth_state(state: str) -> Optional[str]:
    """Retrieve OAuth state data."""
    key = f"oauth:state:{state}"
    return await get(key)


async def delete_oauth_state(state: str) -> bool:
    """Delete OAuth state after use."""
    key = f"oauth:state:{state}"
    return await delete(key)

