"""In-process async trigger bus.

HR events (onboarding spawn, offboarding fire, etc.) are published through this
bus.  It is deliberately simple: handlers register at import time and are
invoked synchronously in registration order when `fire()` is called.

Persisted / cross-process delivery is Plan 3's problem.
"""
from typing import Awaitable, Callable


Handler = Callable[[dict], Awaitable[None]]


class TriggerBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def on(self, event: str) -> Callable[[Handler], Handler]:
        def _wrap(fn: Handler) -> Handler:
            self._handlers.setdefault(event, []).append(fn)
            return fn

        return _wrap

    async def fire(self, event: str, payload: dict) -> None:
        for fn in self._handlers.get(event, []):
            await fn(payload)


# Process-wide singleton.  Handlers register at import time.
trigger_bus = TriggerBus()
