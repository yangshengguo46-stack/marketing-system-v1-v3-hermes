"""Hermes product-owned periodic tasks driven by the native Cron trigger.

Cron owns *when* a tick occurs; each product owner keeps its own due-state and
execution semantics.  This module is intentionally a tiny dispatch registry,
not a second scheduler and not a place for marketing business logic.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from typing import Any


logger = logging.getLogger(__name__)
_LOCK = threading.RLock()
_RUNNING = False
_POOL: concurrent.futures.ThreadPoolExecutor | None = None


def _get_pool() -> concurrent.futures.ThreadPoolExecutor:
    global _POOL
    with _LOCK:
        if _POOL is None:
            _POOL = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="hermes-product-cron"
            )
        return _POOL


def _run_registered_tasks() -> list[dict[str, Any]]:
    """Call product owners that currently have an executable provider."""

    results: list[dict[str, Any]] = []
    try:
        from agent.marketing.metric_loop import reconcile_observed_metric_checkpoints

        results.append(
            {
                "task": "marketing_metric_reconciliation",
                "result": reconcile_observed_metric_checkpoints(),
            }
        )
    except Exception as exc:
        logger.error("Metric reconciliation Cron task failed: %s", exc, exc_info=True)
        results.append(
            {
                "task": "marketing_metric_reconciliation",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    try:
        from agent.marketing.metric_loop import has_due_metric_collection_support

        if has_due_metric_collection_support():
            from agent.marketing.metric_loop import run_due_metric_checkpoints

            results.append(
                {"task": "marketing_metric_checkpoints", "result": run_due_metric_checkpoints()}
            )
    except Exception as exc:
        logger.error("Product Cron task failed: %s", exc, exc_info=True)
        results.append(
            {
                "task": "marketing_metric_checkpoints",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    try:
        from agent.marketing.knowledge_loop import run_knowledge_maintenance

        results.append(
            {
                "task": "marketing_knowledge_maintenance",
                "result": run_knowledge_maintenance(),
            }
        )
    except Exception as exc:
        logger.error("Knowledge maintenance Cron task failed: %s", exc, exc_info=True)
        results.append(
            {
                "task": "marketing_knowledge_maintenance",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    try:
        from agent.human_observer import run_human_observer_maintenance

        results.append(
            {
                "task": "human_observer_maintenance",
                "result": run_human_observer_maintenance(),
            }
        )
    except Exception as exc:
        logger.error("Human observation Cron task failed: %s", exc, exc_info=True)
        results.append(
            {
                "task": "human_observer_maintenance",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    try:
        from agent.marketing.providers.knowledge_sync import (
            has_knowledge_sync_provider,
            run_knowledge_sync,
        )

        if has_knowledge_sync_provider():
            results.append(
                {"task": "marketing_knowledge_sync", "result": run_knowledge_sync()}
            )
    except Exception as exc:
        logger.error("Knowledge sync Cron task failed: %s", exc, exc_info=True)
        results.append(
            {
                "task": "marketing_knowledge_sync",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return results


def run_product_tasks(*, sync: bool = False) -> list[dict[str, Any]] | None:
    """Run once synchronously or dispatch without blocking the Cron ticker."""

    global _RUNNING
    if sync:
        return _run_registered_tasks()
    with _LOCK:
        if _RUNNING:
            return None
        _RUNNING = True

    def _run_and_release() -> None:
        global _RUNNING
        try:
            _run_registered_tasks()
        finally:
            with _LOCK:
                _RUNNING = False

    _get_pool().submit(_run_and_release)
    return None
