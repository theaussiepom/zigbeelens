"""SSE broadcaster queue bounds."""

from __future__ import annotations

import asyncio

import pytest

from zigbeelens.mqtt.events import EventBroadcaster, _MAX_SSE_QUEUE_SIZE


@pytest.mark.asyncio
async def test_sse_queue_drops_oldest_when_full():
    broadcaster = EventBroadcaster()
    loop = asyncio.get_running_loop()
    broadcaster.set_loop(loop)

    async def collect_one() -> dict:
        async for item in broadcaster.subscribe():
            return item

    task = asyncio.create_task(collect_one())
    await asyncio.sleep(0.01)

    for i in range(_MAX_SSE_QUEUE_SIZE + 5):
        broadcaster.publish_sync("dashboard_updated", {"type": "dashboard_updated", "seq": i})

    await asyncio.sleep(0.05)
    item = await asyncio.wait_for(task, timeout=1.0)
    assert item["event"] == "dashboard_updated"
    assert item["data"]["seq"] >= 5


@pytest.mark.asyncio
async def test_slow_client_can_miss_exact_event_but_receive_dashboard_companion():
    broadcaster = EventBroadcaster()
    broadcaster.set_loop(asyncio.get_running_loop())
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=_MAX_SSE_QUEUE_SIZE)
    broadcaster._queues.append(queue)

    broadcaster.publish_sync(
        "home_assistant_enrichment_updated",
        {"type": "home_assistant_enrichment_updated"},
    )
    for sequence in range(_MAX_SSE_QUEUE_SIZE):
        broadcaster.publish_sync("filler", {"type": "filler", "seq": sequence})
    broadcaster.publish_sync(
        "dashboard_updated",
        {
            "type": "dashboard_updated",
            "causes": ["home_assistant_enrichment_updated"],
        },
    )
    # Drain call_soon_threadsafe callbacks without relying on elapsed time.
    await asyncio.sleep(0)

    delivered = []
    while not queue.empty():
        delivered.append(queue.get_nowait())
    event_names = [item["event"] for item in delivered]

    assert len(delivered) == _MAX_SSE_QUEUE_SIZE
    assert "home_assistant_enrichment_updated" not in event_names
    assert delivered[-1] == {
        "event": "dashboard_updated",
        "data": {
            "type": "dashboard_updated",
            "causes": ["home_assistant_enrichment_updated"],
        },
    }


def test_dashboard_event_includes_only_categorical_rebuild_causes(
    monkeypatch: pytest.MonkeyPatch,
):
    broadcaster = EventBroadcaster()
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        broadcaster,
        "publish_sync",
        lambda event, data: published.append((event, data)),
    )

    broadcaster.publish_dashboard_update(
        '{"generated_at":"2026-07-24T00:00:00+00:00"}',
        causes=("health_updated", "home_assistant_enrichment_updated"),
    )

    assert published == [
        (
            "dashboard_updated",
            {
                "type": "dashboard_updated",
                "dashboard": {
                    "generated_at": "2026-07-24T00:00:00+00:00"
                },
                "causes": [
                    "health_updated",
                    "home_assistant_enrichment_updated",
                ],
            },
        )
    ]
