"""Thin async wrapper that lets callers `await` a specific JobResult.

The JobResult itself lives on the controller's shared_handler_variable
(written by `handle_job_result_message` in main.py — same pattern as the
V2 controller). JobTracker doesn't keep its own copy; it just polls the
shared dict for a matching job_id and returns the message when it appears.

Usage:
    tracker = JobTracker(controller)
    result  = await tracker.wait_for("ORD-001-1x1-pp1-transport")
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ClassesAndBuilderMethods.InformationModels import MessageStructure as MS


class JobTracker:

    def __init__(self, controller) -> None:
        """Args:
            controller: MQTTClientController whose shared_handler_variable
                holds {"job_result": {shell_iri: {actor: JobResultMessage}}}.
        """
        self.controller = controller

    async def wait_for(
        self,
        job_id: str,
        timeout: float = 120.0,
        poll: float = 0.2,
    ) -> MS.JobResultMessage:
        """Block until a JobResultMessage with `job_id` appears anywhere in
        the controller's shared_handler_variable["job_result"]. Returns it.

        Raises:
            TimeoutError: if nothing arrives within `timeout` seconds.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            msg = self._find(job_id)
            if msg is not None:
                return msg
            await asyncio.sleep(poll)
        raise TimeoutError(f"No JobResult received for {job_id} within {timeout}s")

    def latest(self, shell_iri: str, actor_name: str) -> MS.JobResultMessage | None:
        """Most recent JobResult from this (shell, actor), or None."""
        jr = self.controller.shared_handler_variable.get("job_result", {})
        return jr.get(shell_iri, {}).get(actor_name)

    def _find(self, job_id: str) -> MS.JobResultMessage | None:
        """Scan the shared dict for a message with this job_id."""
        jr = self.controller.shared_handler_variable.get("job_result", {})
        for by_actor in jr.values():
            for msg in by_actor.values():
                if getattr(msg, "job_id", None) == job_id:
                    return msg
        return None
