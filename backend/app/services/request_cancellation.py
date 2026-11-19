import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from fastapi import Request

T = TypeVar("T")

async def await_or_cancel_on_disconnect(request: Request, operation: Awaitable[T]) -> T:
    """Cancel an async operation when the client disconnects."""
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise asyncio.CancelledError("Client disconnected")
            await asyncio.wait({task}, timeout=0.2)
        return await task
    except asyncio.CancelledError:
        if not task.done():
            task.cancel()
        raise
