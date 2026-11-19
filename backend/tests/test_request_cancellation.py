import asyncio
from types import SimpleNamespace

import pytest

from app.services.request_cancellation import await_or_cancel_on_disconnect


def test_disconnect_cancels_in_flight_operation():
    async def run_test():
        checks = 0
        cancelled = asyncio.Event()

        async def disconnected():
            nonlocal checks
            checks += 1
            return checks >= 2

        async def operation():
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        request = SimpleNamespace(is_disconnected=disconnected)
        with pytest.raises(asyncio.CancelledError):
            await await_or_cancel_on_disconnect(request, operation())
        assert cancelled.is_set()

    asyncio.run(run_test())
