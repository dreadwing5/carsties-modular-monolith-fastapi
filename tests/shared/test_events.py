from dataclasses import dataclass

import pytest

from carsties.shared.events import EventBus, Fault


@dataclass
class SomethingHappened:
    value: str = "x"


@dataclass
class SomethingElseHappened:
    value: str = "y"


async def test_publish_reaches_subscriber():
    bus = EventBus()
    received = []
    bus.subscribe(SomethingHappened, lambda e: _collect(received, e))

    await bus.publish(SomethingHappened("hello"))

    assert [e.value for e in received] == ["hello"]


async def test_publish_only_reaches_matching_event_type():
    bus = EventBus()
    received = []
    bus.subscribe(SomethingHappened, lambda e: _collect(received, e))

    await bus.publish(SomethingElseHappened())

    assert received == []


async def test_failing_handler_publishes_fault():
    bus = EventBus()
    faults = []

    async def failing(event):
        raise ValueError("boom")

    bus.subscribe(SomethingHappened, failing)
    bus.subscribe(Fault, lambda f: _collect(faults, f))

    await bus.publish(SomethingHappened())

    assert len(faults) == 1
    assert isinstance(faults[0].message, SomethingHappened)
    assert isinstance(faults[0].exception, ValueError)


async def test_fault_subscription_filters_by_message_type():
    bus = EventBus()
    faults = []

    async def failing(event):
        raise ValueError("boom")

    bus.subscribe(SomethingHappened, failing)
    bus.subscribe(SomethingElseHappened, failing)
    bus.subscribe_fault(SomethingHappened, lambda f: _collect(faults, f))

    await bus.publish(SomethingHappened())
    await bus.publish(SomethingElseHappened())

    assert len(faults) == 1
    assert isinstance(faults[0].message, SomethingHappened)


async def test_retries_before_faulting():
    bus = EventBus()
    attempts = []

    async def flaky(event):
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("boom")

    bus.subscribe(SomethingHappened, flaky, retries=5, retry_delay=0)

    await bus.publish(SomethingHappened())

    assert len(attempts) == 3


async def test_faulted_fault_handler_does_not_recurse():
    bus = EventBus()

    async def failing(event):
        raise ValueError("boom")

    async def failing_fault_handler(fault):
        raise RuntimeError("fault handler broke too")

    bus.subscribe(SomethingHappened, failing)
    bus.subscribe(Fault, failing_fault_handler)

    await bus.publish(SomethingHappened())  # must not raise or loop forever


async def _collect(sink: list, event) -> None:
    sink.append(event)


@pytest.fixture(autouse=True)
def _quiet_fault_logs(caplog):
    caplog.set_level("CRITICAL", logger="carsties.shared.events")
