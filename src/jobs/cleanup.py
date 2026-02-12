from __future__ import annotations

import asyncio
import logging

from storage.repository import Repository

logger = logging.getLogger(__name__)


class CleanupJob:
    def __init__(self, repository: Repository, retention_days: int, interval_hours: int = 24) -> None:
        self.repository = repository
        self.retention_days = retention_days
        self.interval_hours = interval_hours
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._task:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while self._running:
            removed = self.repository.delete_older_than_days(self.retention_days)
            if removed:
                logger.info("Cleanup removed %d files", len(removed))
            await asyncio.sleep(self.interval_hours * 3600)
