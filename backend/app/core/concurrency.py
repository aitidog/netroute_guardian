"""Concurrency primitives for CPU-bound pipelines and I/O-bound device polling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Literal, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class PipelineExecutor:
    """Offloads CPU-bound routing pipelines off the FastAPI asyncio event loop.

    Supports three execution backends:
    - ``process``: True multi-core parallelism via ``ProcessPoolExecutor`` (ideal for
      large BGP / SD-WAN tables with tens or hundreds of thousands of prefixes).
    - ``thread``: ``ThreadPoolExecutor`` fallback for constrained containers.
    - ``sync``: Direct in-process execution (convenient for deterministic unit tests).
    """

    def __init__(
        self,
        mode: Literal["process", "thread", "sync"] = "process",
        max_workers: int = 4,
    ) -> None:
        self.mode = mode
        self.max_workers = max(1, max_workers)
        self._pool: Executor | None = None

    def start(self) -> None:
        """Lazily initialize the underlying worker pool."""
        if self._pool is not None or self.mode == "sync":
            return
        if self.mode == "process":
            self._pool = ProcessPoolExecutor(max_workers=self.max_workers)
        elif self.mode == "thread":
            self._pool = ThreadPoolExecutor(max_workers=self.max_workers)
        logger.info(
            "PipelineExecutor initialized (mode=%s, max_workers=%d)",
            self.mode,
            self.max_workers,
        )

    def shutdown(self) -> None:
        """Gracefully terminate worker processes or threads."""
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=False)
            self._pool = None
            logger.info("PipelineExecutor shut down")

    async def run(self, fn: Callable[P, T], *args: P.args) -> T:
        """Execute a pure, picklable pipeline function asynchronously.

        Note: Keyword arguments are intentionally passed via a single config/input object
        when using ``ProcessPoolExecutor`` because ``loop.run_in_executor`` takes positional args.
        """
        if self.mode == "sync":
            return fn(*args)

        if self._pool is None:
            self.start()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, fn, *args)

    async def run_batch(
        self,
        fn: Callable[..., T],
        items: list[tuple],
    ) -> list[T]:
        """Fan out multiple independent pipeline computations concurrently across workers."""
        if not items:
            return []
        tasks = [self.run(fn, *arg_tuple) for arg_tuple in items]
        return list(await asyncio.gather(*tasks))


async def gather_with_concurrency(
    limit: int,
    coros: list[Awaitable[T]],
    timeout_seconds: float | None = None,
) -> list[T | BaseException]:
    """Run I/O-bound coroutines concurrently with a bounded semaphore and per-task timeout.

    Individual task failures or timeouts are captured as exception instances rather than
    cancelling sibling device collections (partial-failure isolation).
    """
    semaphore = asyncio.Semaphore(max(1, limit))

    async def _bounded(coro: Awaitable[T]) -> T:
        async with semaphore:
            if timeout_seconds is not None:
                return await asyncio.wait_for(coro, timeout=timeout_seconds)
            return await coro

    return list(await asyncio.gather(*(_bounded(c) for c in coros), return_exceptions=True))
