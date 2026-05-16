"""In-process event bus for roadmap progress updates.

Emitters call `notify()` after stars/mastery change.
SSE subscribers yield updates to connected clients.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field


@dataclass
class ProgressUpdate:
    node_id: uuid.UUID
    folder_id: uuid.UUID
    mastery: float | None
    confidence: float | None
    stars: int

    def to_sse(self) -> str:
        payload = json.dumps({
            "node_id": str(self.node_id),
            "folder_id": str(self.folder_id),
            "mastery": self.mastery,
            "confidence": self.confidence,
            "stars": self.stars,
        })
        return f"event: progress\ndata: {payload}\n\n"


@dataclass
class _ProgressBus:
    """Simple pub/sub: folder_id → set of asyncio.Queue."""
    _subscribers: dict[uuid.UUID, set[asyncio.Queue]] = field(default_factory=dict)

    def subscribe(self, folder_id: uuid.UUID) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(folder_id, set()).add(q)
        return q

    def unsubscribe(self, folder_id: uuid.UUID, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(folder_id)
        if subs:
            subs.discard(q)
            if not subs:
                del self._subscribers[folder_id]

    def notify(self, update: ProgressUpdate) -> None:
        for q in self._subscribers.get(update.folder_id, set()):
            try:
                q.put_nowait(update)
            except asyncio.QueueFull:
                pass  # drop if client is slow


# Singleton
progress_bus = _ProgressBus()
