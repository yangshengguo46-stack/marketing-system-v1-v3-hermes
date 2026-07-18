"""Bounded parallel dispatcher for durable Harness Steps."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from agent.harness.repository import HarnessRepository


class RetryableStepError(RuntimeError):
    def __init__(self, message: str, *, delay_seconds: float = 0):
        super().__init__(message)
        self.delay_seconds = max(0.0, float(delay_seconds))


class PermanentStepError(RuntimeError):
    pass


@dataclass(frozen=True)
class StepResult:
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: Sequence[dict[str, Any]] = field(default_factory=tuple)
    receipts: Sequence[dict[str, Any]] = field(default_factory=tuple)


@dataclass(frozen=True)
class StepExecutionContext:
    repository: HarnessRepository
    workflow: Mapping[str, Any]
    step: Mapping[str, Any]
    attempt_id: str
    lease_token: str
    worker_id: str
    lease_seconds: int

    def heartbeat(self) -> None:
        self.repository.heartbeat(
            step_id=str(self.step["id"]),
            lease_token=self.lease_token,
            extend_seconds=self.lease_seconds,
        )


StepHandler = Callable[[StepExecutionContext], StepResult | dict[str, Any] | None]


class HarnessDispatcher:
    """Claim only registered Step kinds and run them with bounded concurrency."""

    def __init__(
        self,
        repository: HarnessRepository,
        *,
        handlers: Mapping[str, StepHandler] | None = None,
        max_concurrency: int = 3,
        lease_seconds: int = 900,
        worker_prefix: str = "harness-worker",
    ):
        self.repository = repository
        self.handlers: dict[str, StepHandler] = dict(handlers or {})
        self.max_concurrency = max(1, min(int(max_concurrency), 32))
        self.lease_seconds = max(15, min(int(lease_seconds), 86_400))
        self.worker_prefix = str(worker_prefix or "harness-worker")[:120]
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_concurrency,
            thread_name_prefix=self.worker_prefix,
        )
        self._lock = threading.Lock()
        self._active: dict[Future[None], str] = {}
        self._closed = False

    def register(self, step_kind: str, handler: StepHandler) -> None:
        kind = str(step_kind or "").strip()
        if not kind:
            raise ValueError("step_kind is required")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self.handlers[kind] = handler

    def dispatch_once(self, *, workflow_id: str = "") -> int:
        """Reap completed work and fill all currently free worker slots."""

        with self._lock:
            if self._closed:
                raise RuntimeError("dispatcher is closed")
            self._reap_locked()
            available = self.max_concurrency - len(self._active)
        if available <= 0 or not self.handlers:
            return 0

        submitted = 0
        for _ in range(available):
            worker_id = f"{self.worker_prefix}:{uuid.uuid4().hex[:12]}"
            claim = self.repository.claim_ready_step(
                worker_id=worker_id,
                workflow_id=workflow_id,
                lease_seconds=self.lease_seconds,
                runner={"kind": "python.handler", "dispatcher": self.worker_prefix},
                step_kinds=tuple(self.handlers),
            )
            if claim is None:
                break
            handler = self.handlers[str(claim["kind"])]
            future = self._executor.submit(self._execute, claim, handler, worker_id)
            with self._lock:
                self._active[future] = str(claim["id"])
            submitted += 1
        return submitted

    def wait_for_idle(self, *, timeout: float | None = None) -> None:
        """Wait for the current wave; callers dispatch again after DAG promotion."""

        with self._lock:
            futures = list(self._active)
        for future in futures:
            future.result(timeout=timeout)
        with self._lock:
            self._reap_locked()

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def _reap_locked(self) -> None:
        for future in [future for future in self._active if future.done()]:
            self._active.pop(future, None)
            future.result()

    def _execute(
        self, claim: dict[str, Any], handler: StepHandler, worker_id: str
    ) -> None:
        step_id = str(claim["id"])
        lease_token = str(claim["lease_token"])
        attempt_id = str(claim["attempt_id"])
        workflow = self.repository.get_workflow(str(claim["workflow_id"]))
        context = StepExecutionContext(
            repository=self.repository,
            workflow=workflow,
            step=claim,
            attempt_id=attempt_id,
            lease_token=lease_token,
            worker_id=worker_id,
            lease_seconds=self.lease_seconds,
        )
        stop_heartbeat = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(context, stop_heartbeat),
            daemon=True,
            name=f"{self.worker_prefix}-heartbeat",
        )
        try:
            self.repository.start_step(step_id=step_id, lease_token=lease_token)
            heartbeat.start()
            raw = handler(context)
            if raw is None:
                result = StepResult()
            elif isinstance(raw, StepResult):
                result = raw
            elif isinstance(raw, dict):
                result = StepResult(output=raw)
            else:
                raise PermanentStepError("Step handler returned an unsupported result")
            for receipt in result.receipts:
                if not isinstance(receipt, dict):
                    raise PermanentStepError("Step receipt must be an object")
                self.repository.record_receipt(
                    workflow_id=str(claim["workflow_id"]),
                    step_id=step_id,
                    attempt_id=attempt_id,
                    receipt_kind=str(receipt.get("kind") or "activity"),
                    idempotency_key=str(receipt.get("idempotency_key") or ""),
                    input=(
                        receipt.get("input")
                        if isinstance(receipt.get("input"), dict)
                        else {}
                    ),
                    status=str(receipt.get("status") or "completed"),
                    output=(
                        receipt.get("output")
                        if isinstance(receipt.get("output"), dict)
                        else {}
                    ),
                    error=(
                        receipt.get("error")
                        if isinstance(receipt.get("error"), dict)
                        else {}
                    ),
                )
            self.repository.complete_step(
                step_id=step_id,
                lease_token=lease_token,
                output=result.output,
                artifacts=result.artifacts,
            )
        except RetryableStepError as exc:
            self.repository.fail_step(
                step_id=step_id,
                lease_token=lease_token,
                error={"code": "retryable_handler_error", "message": str(exc)},
                retryable=True,
                retry_delay_seconds=exc.delay_seconds,
            )
        except BaseException as exc:
            self.repository.fail_step(
                step_id=step_id,
                lease_token=lease_token,
                error={"code": "handler_error", "message": str(exc)},
                retryable=False,
            )
        finally:
            stop_heartbeat.set()
            if heartbeat.is_alive():
                heartbeat.join(timeout=1)

    @staticmethod
    def _heartbeat_loop(
        context: StepExecutionContext, stop: threading.Event
    ) -> None:
        interval = max(5.0, context.lease_seconds / 3)
        while not stop.wait(interval):
            try:
                context.heartbeat()
            except Exception:
                return
