import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from app.repositories.rpa_repository import RpaProcess

logger = logging.getLogger("rpa_bot.rpa_service")

OnStartCallback = Callable[["QueuedTask"], Awaitable[None]]
OnCompleteCallback = Callable[["QueuedTask", bool, str], Awaitable[None]]


@dataclass
class QueuedTask:
    process: RpaProcess
    chat_id: int
    username: str
    on_start: OnStartCallback
    on_complete: OnCompleteCallback


class RpaService:
    def __init__(
        self,
        uirobot_exe: str,
        uirobot_args: str,
        max_queue_size: int,
    ) -> None:
        self._uirobot_exe = uirobot_exe
        # Build arg list once: ["execute", "--file"] from "execute --file"
        self._uirobot_args: List[str] = uirobot_args.split()
        self._queue: asyncio.Queue[QueuedTask] = asyncio.Queue(maxsize=max_queue_size)
        self._current: Optional[QueuedTask] = None
        self._worker_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._worker_task = asyncio.create_task(self._worker(), name="rpa-worker")
        logger.info("RPA worker started (max_queue=%d)", self._queue.maxsize)

    async def enqueue(
        self,
        process: RpaProcess,
        chat_id: int,
        username: str,
        on_start: OnStartCallback,
        on_complete: OnCompleteCallback,
    ) -> bool:
        """Adds a process to the execution queue. Returns False if the queue is full."""
        if self._queue.full():
            logger.warning(
                "Queue is full (%d/%d) — rejected '%s' from '%s'",
                self._queue.qsize(),
                self._queue.maxsize,
                process.name,
                username,
            )
            return False

        task = QueuedTask(
            process=process,
            chat_id=chat_id,
            username=username,
            on_start=on_start,
            on_complete=on_complete,
        )
        await self._queue.put(task)
        logger.info(
            "Enqueued '%s' for '%s' — queue size: %d/%d",
            process.name,
            username,
            self._queue.qsize(),
            self._queue.maxsize,
        )
        return True

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._current is not None

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _worker(self) -> None:
        while True:
            task = await self._queue.get()
            self._current = task
            try:
                logger.info(
                    "Starting process '%s' requested by '%s'",
                    task.process.name,
                    task.username,
                )
                await task.on_start(task)

                success, output = await self._execute(task.process)

                logger.info(
                    "Process '%s' finished — success=%s",
                    task.process.name,
                    success,
                )
                await task.on_complete(task, success, output)

            except Exception as exc:
                logger.exception(
                    "Unhandled error during '%s': %s", task.process.name, exc
                )
                try:
                    await task.on_complete(task, False, str(exc))
                except Exception:
                    pass
            finally:
                self._current = None
                self._queue.task_done()

    async def _execute(self, process: RpaProcess) -> tuple:
        """Runs UiRobot.exe via subprocess (handles paths with spaces safely)."""
        cmd = [self._uirobot_exe] + self._uirobot_args + [process.nupkg_path]
        logger.debug("Executing: %s", " ".join(f'"{c}"' if " " in c else c for c in cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            output = (
                stdout.decode("utf-8", errors="replace")
                + stderr.decode("utf-8", errors="replace")
            ).strip()

            success = proc.returncode == 0

            if not success:
                logger.error(
                    "Process '%s' exited with code %d.\nOutput:\n%s",
                    process.name,
                    proc.returncode,
                    output,
                )

            return success, output

        except Exception as exc:
            logger.exception("Subprocess error for '%s': %s", process.name, exc)
            return False, str(exc)
