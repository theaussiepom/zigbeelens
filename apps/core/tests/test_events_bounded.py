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
