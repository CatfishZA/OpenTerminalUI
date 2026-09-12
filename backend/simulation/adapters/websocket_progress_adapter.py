from __future__ import annotations

from typing import Any, Awaitable, Callable


class WebsocketProgressAdapter:
    def __init__(self, publish: Callable[[str, dict[str, Any]], Awaitable[None]]):
        self._publish = publish

    async def update(self, run_id: str, *, progress: int, stage: str, status: str) -> None:
        if not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")
        await self._publish(
            f"simulation:{run_id}",
            {"run_id": run_id, "progress": progress, "stage": stage, "status": status},
        )
