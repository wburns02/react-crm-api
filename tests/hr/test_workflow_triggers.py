import pytest

from app.hr.workflow.triggers import TriggerBus


@pytest.mark.asyncio
async def test_trigger_bus_dispatches():
    bus = TriggerBus()
    calls: list[dict] = []

    @bus.on("hr.test.fired")
    async def handler(payload: dict) -> None:
        calls.append(payload)

    await bus.fire("hr.test.fired", {"x": 1})
    assert calls == [{"x": 1}]


@pytest.mark.asyncio
async def test_trigger_bus_ignores_unknown_events():
    bus = TriggerBus()
    # Firing an event with no handlers is a no-op, not an error.
    await bus.fire("hr.does.not.exist", {})


@pytest.mark.asyncio
async def test_multiple_handlers_all_fire():
    bus = TriggerBus()
    seen: list[str] = []

    @bus.on("hr.ev")
    async def a(payload: dict) -> None:
        seen.append("a")

    @bus.on("hr.ev")
    async def b(payload: dict) -> None:
        seen.append("b")

    await bus.fire("hr.ev", {})
    assert seen == ["a", "b"]
