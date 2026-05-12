"""Tracks JobResult messages and lets callers `await` a specific job.

Stations publish `JobResultMessage` to their `JobResult/<actor>` topic when a
command finishes. The Line Controller correlates results to commands by
`job_id`, which uses the format `{order_id}-{step_id}`.

Usage:
    tracker = JobTracker()
    controller.register_handler(MS.JobResultMessage, tracker.make_handler())
    ...
    result = await tracker.wait_for(job_id)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS


class JobTracker:
    """In-memory store of every JobResultMessage seen on the line, indexed by job_id."""

    def __init__(self) -> None:
        self.results: dict[str, MS.JobResultMessage] = {}

    def record(self, message: MS.JobResultMessage) -> None:
        self.results[message.job_id] = message

    async def wait_for(
        self,
        job_id: str,
        timeout: float = 120.0,
        poll: float = 0.2,
    ) -> MS.JobResultMessage:
        """Block until the JobResult for this job_id arrives, then return it.

        Raises:
            TimeoutError: if nothing arrives within `timeout` seconds.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if job_id in self.results:
                return self.results[job_id]
            await asyncio.sleep(poll)
        raise TimeoutError(f"No JobResult received for {job_id} within {timeout}s")

    def make_handler(self):
        """Build the MQTT handler closure to pass to controller.register_handler()."""
        def handle(controller, message: MS.JobResultMessage, topic_info) -> None:
            self.record(message)
            print(
                f"[jobresult] {message.job_id}  result={message.result.value} "
                f"quality={message.quality.value}"
            )
        return handle
