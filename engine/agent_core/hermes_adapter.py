"""Durable product adapter for the Hermes source runtime.

The adapter owns product task/session projections while Hermes owns the model
loop and transcript database.  It never shells out to the Hermes CLI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from .models import TaskStatus
from .policy import set_authorization_checker
from .store import AgentCoreStore
from .tool_gateway import ensure_registered, set_task_context
from .tool_manifest import all_tools, tool_by_name

logger = logging.getLogger("marketing-os.adapter")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentSession:
    session_id: str
    user_id: str
    workspace: str | None
    created_at: str
    active_task_id: str | None = None


class HermesAgentService:
    """Long-lived source runtime with durable product sessions and events."""

    _PLAN_RE = re.compile(r'^\s*(\d+)[\.\)、）]\s*(.+)$', re.MULTILINE)

    _TOOL_KEYWORDS: list[tuple[list[str], str]] = [
        (["趋势", "热点", "热榜", "热搜"], "marketing_read_trends"),
        (["登录", "账号", "状态", "会话"], "marketing_read_accounts"),
        (["搜索", "采集", "抖音", "内容", "抓取", "关键词", "行业"], "marketing_trending_search"),
        (["选题", "建议", "内容"], "marketing_read_suggestions"),
        (["指标", "同步", "粉丝", "点赞", "播放"], "marketing_accounts_sync"),
        (["画像", "配置", "简介"], "marketing_read_profiles"),
        (["发布", "发布任务"], "marketing_read_publishing_tasks"),
        (["概览", "仪表盘", "仪表板"], "marketing_read_dashboard"),
        (["巡检", "报告", "情报"], "marketing_read_intelligence_report"),
    ]

    PRODUCT_EVENT_TYPES = {
        "status", "notice", "notice.clear", "context.compressed",
        "provider.fallback", "model.changed",
    }

    def __init__(
        self,
        store: AgentCoreStore,
        *,
        hermes_home: str | Path,
        agent_root: str | Path,
        provider_env: dict[str, str] | None = None,
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        enabled_toolsets: list[str] | None = None,
    ):
        self._store = store
        self._hermes_home = Path(hermes_home)
        self._agent_root = Path(agent_root)
        self._provider_env = provider_env or {}
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._enabled_toolsets = enabled_toolsets or ["marketing-desktop", "memory"]
        self._lock = threading.RLock()
        self._task_threads: dict[str, threading.Thread] = {}
        self._task_agents: dict[str, Any] = {}
        self._session_auths: dict[str, dict[str, dict[str, Any]]] = {}

        set_authorization_checker(self._store.is_authorized)

        self._configure_runtime_imports()
        self._hermes_home.mkdir(parents=True, exist_ok=True)
        from hermes_state import SessionDB
        self._session_db = SessionDB(db_path=self._hermes_home / "state.db")

        self._sessions: dict[str, AgentSession] = {}
        for row in self._store.list_sessions():
            self._sessions[row["id"]] = AgentSession(
                session_id=row["id"],
                user_id=row["user_id"],
                workspace=row.get("workspace"),
                created_at=row["created_at"],
                active_task_id=row.get("active_task_id"),
            )

        # A process loss must not masquerade as a still-running worker. Keep the
        # same task and checkpoint, but make the interruption explicit and resumable.
        for task in self._store.list_tasks({TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.RETRYING}):
            try:
                self._store.transition_task(
                    task["id"], TaskStatus.PAUSED,
                    checkpoint={**task.get("checkpoint", {}), "runtime_interrupted_at": _now()},
                    error="Agent runtime restarted; task is ready to resume",
                )
                self._emit(task["id"], "task.paused", reason="runtime_restarted")
            except (KeyError, ValueError):
                logger.exception("failed to pause interrupted task %s", task["id"])

    def _configure_runtime_imports(self) -> None:
        paths = [self._agent_root]
        site_packages = (
            self._agent_root / ".venv" / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        )
        if site_packages.exists():
            paths.append(site_packages)
        for path in reversed(paths):
            value = str(path)
            if value not in sys.path:
                sys.path.insert(0, value)

    async def create_session(self, user_id: str, workspace: str | None = None) -> dict:
        row = self._store.create_or_get_session(user_id=user_id, workspace=workspace)
        with self._lock:
            session = self._sessions.get(row["id"])
            if session is None:
                session = AgentSession(
                    session_id=row["id"], user_id=row["user_id"], workspace=row.get("workspace"),
                    created_at=row["created_at"], active_task_id=row.get("active_task_id"),
                )
                self._sessions[row["id"]] = session
        return self._session_dict(session)

    async def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            row = self._store.get_session(session_id)
            if row is None:
                return None
            session = AgentSession(
                session_id=row["id"], user_id=row["user_id"], workspace=row.get("workspace"),
                created_at=row["created_at"], active_task_id=row.get("active_task_id"),
            )
            with self._lock:
                self._sessions[session_id] = session
        return self._session_dict(session)

    @staticmethod
    def _session_dict(session: AgentSession) -> dict:
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "workspace": session.workspace,
            "active_task_id": session.active_task_id,
            "created_at": session.created_at,
        }

    def runtime_status(self) -> dict:
        source_available = (self._agent_root / "run_agent.py").exists()
        provider_configured = bool(self._api_key)
        return {
            "available": source_available and provider_configured,
            "backend": "hermes-source",
            "source_available": source_available,
            "provider_configured": provider_configured,
            "toolsets": list(self._enabled_toolsets),
            "tool_count": len(all_tools()),
        }

    async def send_message(self, session_id: str, message: str, account_id: str | None = None) -> dict:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"session not found: {session_id}")
        if session.active_task_id:
            active = self._store.get_task(session.active_task_id)
            if active["status"] not in {"completed", "failed", "cancelled", "paused"}:
                raise RuntimeError(f"session already has an active task: {session.active_task_id}")

        initial_plan = self._build_initial_plan(message, account_id)
        task = self._store.create_task(
            session_id=session_id,
            user_id=session.user_id,
            objective=message,
            account_id=account_id,
            plan=initial_plan,
        )
        self._store.transition_task(task["id"], TaskStatus.PLANNING)
        if initial_plan:
            self._emit(
                task["id"], "plan.ready", plan=initial_plan,
                plan_version=task.get("plan_version", 1), plan_total=len(initial_plan),
                source="product_executor",
            )
        self._bind_task(session, task["id"])
        self._start_task(session, task["id"], message)
        return {"task_id": task["id"], "session_id": session_id, "status": "planning"}

    def _bind_task(self, session: AgentSession, task_id: str | None) -> None:
        with self._lock:
            session.active_task_id = task_id
        self._store.set_session_active_task(session.session_id, task_id)

    def _start_task(self, session: AgentSession, task_id: str, message: str) -> None:
        thread = threading.Thread(
            target=self._run_agent_loop,
            args=(session, task_id, message),
            name=f"hermes-loop-{task_id[:12]}",
            daemon=True,
        )
        with self._lock:
            self._task_threads[task_id] = thread
        thread.start()

    async def stream_events(self, task_id: str) -> AsyncIterator[dict]:
        try:
            self._store.get_task(task_id)
        except KeyError:
            yield {"type": "error", "task_id": task_id, "error": "task not found"}
            yield {"type": "done", "task_id": task_id}
            return

        sequence = 0
        terminal_seen = False
        while True:
            for event in self._store.list_events_after(task_id, sequence):
                sequence = max(sequence, int(event["sequence"]))
                payload = event.get("payload") or {}
                event_type = event["event_type"]
                yield {
                    "type": event_type,
                    "task_id": task_id,
                    "timestamp": event["created_at"],
                    **payload,
                }
                if event_type in {"task.completed", "task.failed", "task.cancelled"}:
                    terminal_seen = True
            task = self._store.get_task(task_id)
            if terminal_seen or task["status"] in {"completed", "failed", "cancelled"}:
                yield {"type": "done", "task_id": task_id, "status": task["status"]}
                return
            await asyncio.sleep(0.25)

    async def get_task_status(self, task_id: str) -> dict:
        try:
            task = self._store.get_task(task_id)
        except KeyError:
            return {"task_id": task_id, "status": "unknown", "error": "task not found"}
        plan = task.get("plan", [])
        return {
            "task_id": task_id,
            "session_id": task["session_id"],
            "status": task["status"],
            "objective": task["objective"],
            "current_step": task.get("current_step"),
            "checkpoint": task.get("checkpoint", {}),
            "plan": plan,
            "plan_version": task.get("plan_version", 1),
            "event_count": len(self._store.list_events(task_id)),
            "retry_count": task.get("retry_count", 0),
            "last_error": task.get("last_error"),
        }

    async def cancel_task(self, task_id: str) -> dict:
        return self._stop_task(task_id, TaskStatus.CANCELLED, "user cancelled")

    async def pause_task(self, task_id: str) -> dict:
        return self._stop_task(task_id, TaskStatus.PAUSED, "user paused")

    def _stop_task(self, task_id: str, target: TaskStatus, reason: str) -> dict:
        with self._lock:
            agent = self._task_agents.get(task_id)
        if agent is not None:
            try:
                agent.interrupt(reason)
            except Exception:
                logger.exception("failed to interrupt Hermes task %s", task_id)

        task = self._store.get_task(task_id)

        # Cancellation and pending-approval invalidation must be one durable
        # transaction.  In particular, WAITING_USER is cancellable.
        if target is TaskStatus.CANCELLED:
            cancelled = self._store.cancel_task_and_void_approvals(
                task_id, reason="task cancelled",
            )
            session = self._sessions.get(task["session_id"])
            if session is not None and session.active_task_id == task_id:
                self._bind_task(session, None)
            return {"task_id": task_id, "status": cancelled["status"]}

        if task["status"] not in {"completed", "failed", "cancelled", "paused", "waiting_user"}:
            self._store.transition_task(task_id, target, error=reason)
            self._emit(task_id, f"task.{target.value}", reason=reason)
        return {"task_id": task_id, "status": target.value}

    async def resume_task(self, task_id: str) -> dict:
        task = self._store.get_task(task_id)
        if task["status"] not in {"paused", "failed", "running", "waiting_user"}:
            raise ValueError(f"task cannot resume from {task['status']}")
        session = self._sessions.get(task["session_id"])
        if session is None:
            raise KeyError(f"session not found: {task['session_id']}")

        plan = task.get("plan", [])
        checkpoint = task.get("checkpoint", {})

        # --- Re-execution guard: mark steps as completed if their effect already executed ---
        executed_effects = checkpoint.get("executed_effects", {})
        if executed_effects:
            for step in plan:
                effect_id = step.get("effect_id")
                if effect_id and effect_id in executed_effects:
                    if step.get("status") not in ("completed", "skipped"):
                        step["status"] = "completed"
            self._store.update_plan(task_id, plan)

        # --- Approval recovery ---
        pending_approval_id = checkpoint.get("pending_approval_id")
        if pending_approval_id:
            try:
                approval = self._store.get_approval(pending_approval_id)
                if approval["status"] == "pending":
                    task_current = self._store.get_task(task_id)
                    if task_current["status"] != "waiting_user":
                        self._store.transition_task(task_id, TaskStatus.WAITING_USER,
                                                     current_step="awaiting_approval")
                        self._emit(task_id, "task.waiting_user",
                                   approval_id=pending_approval_id,
                                   capability=approval.get("capability"),
                                   arguments=approval.get("arguments", {}),
                                   risk_summary=approval.get("risk_summary"))
                    return {"task_id": task_id, "status": "waiting_user", "approval_id": pending_approval_id}
                elif approval["status"] == "expired":
                    for step in plan:
                        if step.get("status") == "running":
                            step["status"] = "skipped"
                    self._store.update_plan(task_id, plan)
            except KeyError:
                pass

        completed_steps = [s for s in plan if s.get("status") == "completed"]
        skipped_steps = [s for s in plan if s.get("status") == "skipped"]
        pending_steps = [s for s in plan if s.get("status") in ("pending", "running")]
        effect_events: list[dict] = []

        if plan and pending_steps:
            completed_desc = "、".join(
                f"步骤{s['id']}: {s['description']}" for s in completed_steps
            ) if completed_steps else "无"
            skipped_desc = ""
            if skipped_steps:
                skipped_parts = [f"步骤{s['id']}: {s['description']}" for s in skipped_steps]
                skipped_desc = "\n已跳过步骤（审批过期）：" + "、".join(skipped_parts)
            next_desc = pending_steps[0]["description"]
            current_idx = len(completed_steps) + len(skipped_steps) + 1
            total = len(plan)
            resume_message = (
                f"继续完成此前中断的目标：{task['objective']}\n\n"
                f"已完成步骤：{completed_desc}{skipped_desc}\n"
                f"当前进度：第{current_idx}/{total}步\n"
                f"下一步：{next_desc}\n\n"
                f"请继续执行，不要重复已完成步骤。已完成步骤的结果已在上下文中。"
            )
        else:
            resume_message = f"继续完成此前中断的目标：{task['objective']}"

        try:
            events = self._store.list_events_after(task_id, 0)
            effect_events = [e for e in events if e["event_type"] == "effect.executed"]
            if effect_events:
                last = effect_events[-1]["payload"]
                receipt = last.get("receipt", {})
                if receipt:
                    resume_message += f"\n\n上一个操作（{last.get('capability', '')}）已完成，结果：{self._summarize_receipt(receipt)}"
                effect_descs = "、".join(
                    f"{e['payload'].get('capability', '')}（已执行）" for e in effect_events
                )
                resume_message += f"\n已执行的效果操作（不得重复执行）：{effect_descs}"
            rejected_events = [
                e for e in events
                if e["event_type"] == "approval.decided"
                and e.get("payload", {}).get("decision") == "rejected"
            ]
            if rejected_events:
                decision = rejected_events[-1]["payload"]
                approval = self._store.get_approval(decision.get("approval_id", ""))
                resume_message += (
                    f"\n\n用户拒绝了操作 {approval.get('capability', '')}。"
                    "不要再次执行或立即重复请求同一授权；请说明影响，并在可能时提供无需该权限的替代方案。"
                )
        except Exception:
            logger.exception("failed to build resume context for %s", task_id)

        if task["status"] == "failed":
            self._store.transition_task(task_id, TaskStatus.RETRYING)
        if task["status"] != "running":
            self._store.transition_task(task_id, TaskStatus.RUNNING, current_step="resuming")

        resume_step = f"{len(completed_steps) + 1}/{len(plan)}" if plan and pending_steps else None
        self._bind_task(session, task_id)
        self._emit(task_id, "task.resumed",
                   checkpoint=task.get("checkpoint", {}),
                   plan=plan, resume_step=resume_step)
        self._start_task(session, task_id, resume_message)
        return {"task_id": task_id, "status": "running"}

    async def replan_task(self, task_id: str, new_objective: str) -> dict:
        """Replan a task with a new objective, keeping completed work."""
        task = self._store.get_task(task_id)
        if task["status"] in ("completed", "cancelled"):
            raise ValueError(f"cannot replan from {task['status']}")
        plan = task.get("plan", [])
        completed = [s for s in plan if s.get("status") == "completed"]
        pending = [s for s in plan if s.get("status") != "completed"]
        # Discard pending steps, keep completed
        new_plan = [
            {**s, "status": "completed", "tool_name": s.get("tool_name") or s.get("tool_guess")}
            for s in completed
        ]
        checkpoint = self._build_checkpoint(task_id)
        self._store.update_plan(task_id, new_plan)
        self._store.update_task_progress(task_id, checkpoint=checkpoint)
        self._emit(task_id, "task.replanned",
                    old_objective=task["objective"], new_objective=new_objective,
                    kept_steps=len(completed), discarded_steps=len(pending),
                    plan_version=task.get("plan_version", 1) + 1)
        return self._store.get_task(task_id)

    async def resume_after_effect(self, task_id: str) -> dict:
        """Resume exactly the task that was waiting for an approved capability.

        The previous Hermes loop normally exits immediately after it observes
        ``waiting_user``.  Join it briefly before installing the replacement
        worker so its cleanup cannot remove the new worker from the registry.
        """
        task = self._store.get_task(task_id)
        if task["status"] != "waiting_user":
            return {"task_id": task_id, "status": task["status"]}
        with self._lock:
            previous = self._task_threads.get(task_id)
        if previous is not None and previous.is_alive():
            await asyncio.to_thread(previous.join, 2.0)
        return await self.resume_task(task_id)

    async def resume_after_rejection(self, task_id: str) -> dict:
        """Continue the conversation after a user rejects a capability."""
        return await self.resume_after_effect(task_id)

    async def decide_approval(self, approval_id: str, approved: bool, reason: str | None = None, *, transition_task: bool = True) -> dict:
        return self._store.decide_approval(approval_id, approved, reason, transition_task=transition_task)

    def _run_agent_loop(self, session: AgentSession, task_id: str, user_message: str) -> None:
        try:
            agent = self._build_agent(session)
            with self._lock:
                self._task_agents[task_id] = agent

            task = self._store.get_task(task_id)
            if task["status"] == "planning":
                self._store.transition_task(task_id, TaskStatus.RUNNING, current_step="planning")
            self._emit(task_id, "task.started")

            history = []
            try:
                if self._session_db.get_session(session.session_id):
                    history = self._session_db.get_messages_as_conversation(session.session_id)
            except Exception:
                logger.exception("failed to restore Hermes transcript %s", session.session_id)

            set_task_context({
                "task_id": task_id, "store": self._store,
                "user_id": session.user_id,
                "account_id": task.get("account_id"),
                "session_auths": self._session_auths.get(session.session_id, set()),
            })
            try:
                authoritative_evidence = self._prefetch_required_evidence(task_id)
                turn_context = self._build_turn_context(
                    session, task.get("account_id"), authoritative_evidence,
                )
                turn_message = f"{turn_context}\n\n用户本轮请求：\n{user_message}"
                persist_user_message = None
                if history:
                    persist_user_message = user_message
                result = agent.run_conversation(
                    turn_message,
                    task_id=task_id,
                    system_message=self._build_system_prompt(session, account_id=task.get("account_id")) if not history else None,
                    conversation_history=history or None,
                    persist_user_message=persist_user_message,
                )
                reply = result.get("final_response", "") if isinstance(result, dict) else str(result)
                violations = self._detect_evidence_violations(
                    reply, authoritative_evidence, task.get("account_id"),
                )
                if violations:
                    self._emit(task_id, "response.repair_requested", violations=violations)
                    repair_message = (
                        f"{turn_context}\n\n"
                        "你上一版草稿未通过产品证据质量检查。请完整重写最终答案，不要解释检查过程，"
                        "也不要再次调用工具。必须修正以下问题：\n- "
                        + "\n- ".join(violations)
                        + "\n\n用户本轮要求仍是：\n" + user_message
                    )
                    repaired = agent.run_conversation(
                        repair_message,
                        task_id=task_id,
                        system_message=None,
                        persist_user_message=None,
                    )
                    reply = repaired.get("final_response", "") if isinstance(repaired, dict) else str(repaired)
                    remaining = self._detect_evidence_violations(
                        reply, authoritative_evidence, task.get("account_id"),
                    )
                    if remaining:
                        self._emit(task_id, "response.rejected", violations=remaining)
                        reply = self._build_grounding_failure_reply(authoritative_evidence)
            finally:
                set_task_context(None)

            current = self._store.get_task(task_id)
            if current["status"] in {"cancelled", "paused"}:
                return
            if current["status"] == TaskStatus.WAITING_USER:
                checkpoint = self._build_checkpoint(task_id)
                self._store.update_task_progress(task_id, checkpoint=checkpoint)
                last_events = self._store.list_events_after(task_id, 0)
                approval_events = [e for e in last_events if e["event_type"] == "approval.requested"]
                if approval_events:
                    payload = approval_events[-1]["payload"]
                    self._emit(task_id, "task.waiting_user",
                               approval_id=payload.get("approval_id"),
                               capability=payload.get("capability"),
                               arguments=payload.get("arguments", {}),
                               risk_summary=payload.get("risk_summary"))
                return
            self._finalize_plan(task_id)
            self._store.transition_task(task_id, TaskStatus.COMPLETED, current_step="completed")
            self._emit(task_id, "task.completed", reply=reply)
            if session.active_task_id == task_id:
                self._bind_task(session, None)
        except Exception as exc:
            logger.exception("agent loop failed task_id=%s", task_id)
            try:
                from .models import classify_error
                category = classify_error(str(exc))
                current = self._store.get_task(task_id)
                if current["status"] not in {"cancelled", "paused"}:
                    if category.retryable and current.get("retry_count", 0) < 3:
                        self._store.transition_task(task_id, TaskStatus.RETRYING, error=str(exc))
                        self._emit(task_id, "task.failed", error=str(exc),
                                   retryable=True, error_category=category.value)
                    else:
                        self._store.transition_task(task_id, TaskStatus.FAILED, error=str(exc))
                        self._emit(task_id, "task.failed", error=str(exc),
                                   retryable=False, error_category=category.value)
            except (KeyError, ValueError):
                logger.exception("failed to persist task failure %s", task_id)
        finally:
            with self._lock:
                if self._task_agents.get(task_id) is locals().get("agent"):
                    self._task_agents.pop(task_id, None)
                if self._task_threads.get(task_id) is threading.current_thread():
                    self._task_threads.pop(task_id, None)

    def _build_agent(self, session: AgentSession) -> Any:
        ensure_registered()
        from run_agent import AIAgent

        def active_task_id() -> str | None:
            return session.active_task_id

        _plan_captured: list[str] = []  # track which tasks already had plan capture attempted

        def on_event(event_type: str, payload: dict) -> None:
            task_id = active_task_id()
            if task_id and event_type in self.PRODUCT_EVENT_TYPES:
                self._emit(task_id, f"runtime.{event_type}", payload=payload if isinstance(payload, dict) else {})

        def on_step(api_call_count: int, previous_tools: list) -> None:
            task_id = active_task_id()
            if not task_id:
                return

            task = self._store.get_task(task_id)
            plan = task.get("plan", [])

            if api_call_count == 1 and not plan and task_id not in _plan_captured:
                _plan_captured.append(task_id)
                captured = self._capture_plan(session.session_id, task["objective"])
                if captured:
                    self._store.update_plan(task_id, captured)
                    task = self._store.get_task(task_id)
                    plan = task.get("plan", [])
                    self._emit(task_id, "plan.ready",
                               plan=plan, plan_version=task.get("plan_version", 1), plan_total=len(plan))

            if plan:
                completed = [s for s in plan if s.get("status") == "completed"]
                running = [s for s in plan if s.get("status") == "running"]
                current = running[0] if running else None
                label = f"{current['id']}/{len(plan)}" if current else f"{len(completed)}/{len(plan)}"
                self._store.update_task_progress(task_id, current_step=label)
                plan_step_id = current["id"] if current else str(len(completed) + 1)
                self._emit(task_id, "step.update", label=label, detail=previous_tools or [],
                           status="running", plan=plan,
                           plan_step_id=plan_step_id,
                           plan_total=len(plan), plan_version=task.get("plan_version", 1))
            else:
                label = f"step-{api_call_count}"
                self._store.update_task_progress(task_id, current_step=label)
                self._emit(task_id, "step.update", label=label, detail=previous_tools or [], status="running")

        def on_tool_start(tool_call_id: str, name: str, arguments: dict) -> None:
            task_id = active_task_id()
            if not task_id:
                return
            try:
                task = self._store.get_task(task_id)
                plan = task.get("plan", [])
                changed = False
                for step in plan:
                    if step.get("kind") == "synthesis":
                        continue
                    if step["status"] == "pending":
                        guess = step.get("tool_name") or step.get("tool_guess")
                        if guess is None or guess == name:
                            step["status"] = "running"
                            step["tool_name"] = name  # backfill with real tool name
                            changed = True
                            break
                if changed:
                    self._store.update_plan(task_id, plan)
                    self._store.update_task_progress(task_id, checkpoint=self._build_checkpoint(task_id))
                    updated = self._store.get_task(task_id)
                    self._emit(task_id, "plan.updated", plan=updated.get("plan", []),
                               plan_version=updated.get("plan_version", 1), plan_total=len(plan))
            except Exception:
                pass
            self._emit(task_id, "tool.started", tool_call_id=tool_call_id, tool=name, arguments=arguments)

        def on_tool_complete(tool_call_id: str, name: str, arguments: dict, result: Any) -> None:
            task_id = active_task_id()
            if not task_id:
                return
            parsed_result: Any = result
            if isinstance(result, str):
                try:
                    parsed_result = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    parsed_result = result[:32_000]
            result_status = parsed_result.get("status") if isinstance(parsed_result, dict) else None
            try:
                task = self._store.get_task(task_id)
                plan = task.get("plan", [])
                changed = False
                if result_status == "ok":
                    for step in plan:
                        if step["status"] == "running":
                            guess = step.get("tool_name") or step.get("tool_guess")
                            if guess is None or guess == name:
                                step["status"] = "completed"
                                changed = True
                                break
                if changed:
                    self._store.update_plan(task_id, plan)
                    # Write deterministic checkpoint
                    ck = self._build_checkpoint(task_id)
                    self._store.update_task_progress(task_id, checkpoint=ck)
                    updated = self._store.get_task(task_id)
                    self._emit(task_id, "plan.updated", plan=updated.get("plan", []),
                               plan_version=updated.get("plan_version", 1), plan_total=len(plan))
            except Exception:
                pass
            self._emit(
                task_id, "tool.completed", tool_call_id=tool_call_id,
                tool=name, arguments=arguments, result=parsed_result,
            )

        return AIAgent(
            base_url=self._base_url or None,
            api_key=self._api_key or None,
            model=self._model,
            session_id=session.session_id,
            session_db=self._session_db,
            enabled_toolsets=list(self._enabled_toolsets),
            event_callback=on_event,
            step_callback=on_step,
            tool_start_callback=on_tool_start,
            tool_complete_callback=on_tool_complete,
            quiet_mode=True,
            tool_progress_mode="minimal",
            save_trajectories=False,
            skip_context_files=True,
            skip_memory=False,
            load_soul_identity=False,
            max_iterations=30,
            checkpoints_enabled=False,
        )

    def _build_system_prompt(self, session: AgentSession, account_id: str | None = None) -> str:
        base = (
            "你是智能营销桌面应用的长期运营智能体。先理解用户真实目标，再决定是否需要营销数据。\n\n"
            "在开始执行工具前，请先输出一个编号计划，格式如下：\n\n"
            "计划：\n"
            "1. 步骤描述\n"
            "2. 步骤描述\n"
            "3. 步骤描述\n\n"
            "输出计划后，按步骤依次执行。\n\n"
            "你可以使用 marketing_draft_memory_add 写入候选营销记忆。候选不会自动进入上下文；"
            "用户确认后，marketing_read_memory_list 才会把它作为当前用户范围内的有效记忆返回。\n\n"
            "边界：\n"
            "- 只能调用 marketing-desktop 工具集，不得使用 Shell、任意文件或系统设置能力。\n"
            "- Cookie、Token 和 Key 由 Electron 持有，你只能看到登录状态和脱敏业务结果。\n"
            "- 产品内可逆写入可直接执行；登录态资源和外部动作必须遵守产品审批与用户授权范围。\n"
            "- 结论必须保留来源、采集时间和置信度；数据不足时直说，不编造。\n"
            "- 输出必须区分三类：『已证实事实』只能复述工具明确返回的字段；『策略推断』必须标注为推断并说明依据；『创作建议』不得冒充已经发生的事实。\n"
            "- industries/监控行业是全局配置，不是账号标签；不得把未读取的账号定位、内容数量、活跃粉丝、转化或增长阶段写成事实。\n"
            "- 多个选题复用同一热点时，必须明确写成『1条证据延展出的多个角度』，不得包装成多条独立热点。\n"
            "- 寒暄自然简短，不主动倾倒营销数据。\n"
            "- 写入记忆前确认不包含 Cookie/Token/密码等秘密信息。\n\n"
            "热点趋势分析规范：\n"
            "- 行业热点/趋势请求优先使用 marketing_read_trends 读取本地已缓存热点，"
            "支持 query/platform/limit 参数；该工具为只读自动允许，无需审批\n"
            "- 回答必须指向可追溯证据：说明数据时间（cached_at）、来源平台（source_platform）、"
            "热点标题（title），URL 存在时保留\n"
            "- 缓存过期（status=stale）时仍可引用分析，但必须声明「使用上次有效缓存」\n"
            "- 无数据（status=no_data）或错误（status=error）时如实告知没有分析依据，不得编造热点\n"
            "- 没有行业匹配结果时返回明确空结果；严禁混入无关娱乐/影视热点充数"
        )
        try:
            memories = self._trusted_memories(session.user_id, workspace=session.workspace)
            if account_id:
                memories = [m for m in memories if not m.get("account_id") or m["account_id"] == account_id]
            else:
                memories = [m for m in memories if not m.get("account_id")]
            if account_id:
                base += f"\n\n当前上下文账号 ID：{account_id}"
            if memories:
                lines = ["\n\n用户已确认的账号/用户信息："]
                for m in memories[:15]:
                    kind_label = {"user": "用户记忆", "account": "账号记忆", "episodic": "项目记忆",
                                  "semantic": "知识", "procedural": "技能"}.get(m.get("kind"), m.get("kind"))
                    extra = f" [账号:{m.get('account_id')}]" if m.get("account_id") else ""
                    lines.append(f"- [{kind_label}{extra}] {m['content']}")
                return base + "\n".join(lines)
        except Exception:
            pass
        return base

    def _trusted_memories(
        self, user_id: str, account_id: str | None = None,
        workspace: str | None = None,
    ) -> list[dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for status in ("verified", "locked"):
            for item in self._store.list_memories(
                user_id=user_id, account_id=account_id, workspace=workspace, status=status,
            ):
                items[item["id"]] = item
        return list(items.values())

    def _build_turn_context(
        self, session: AgentSession, account_id: str | None,
        authoritative_evidence: dict[str, Any] | None = None,
    ) -> str:
        lines = ["<marketing-turn-context>"]
        if account_id:
            lines.append(f"当前账号 ID：{account_id}")
            lines.append("只使用当前账号或全局用户记忆；不要沿用其他账号的定位、指标或结论。")
        else:
            lines.append("当前未指定账号；不要擅自把某个账号的记忆套用到全部账号。")
        lines.extend([
            "本轮证据纪律：",
            "- 已证实事实只能来自本轮工具明确返回字段，并保留来源/时间。",
            "- 以前轮次的助手回答不是证据；若与本轮权威证据冲突，必须丢弃旧说法。",
            "- industries 是全局监控范围，不是账号标签。",
            "- 未读取的账号定位、内容数、活跃度、转化和增长阶段不得写成事实。",
            "- 策略推断必须标注为推断；创作建议必须标注为建议。",
            "- 『全网热议』『全民关注』『自然流量大』『完美匹配』等扩大性判断，除非工具明确给出跨平台数据，否则只能作为不确定推断或删除。",
            "- 多个角度复用同一热点时，明确说明是一条证据的延展。",
        ])
        if authoritative_evidence:
            lines.extend(self._format_authoritative_evidence(authoritative_evidence))
        try:
            memories = self._trusted_memories(session.user_id, account_id, workspace=session.workspace) if account_id else self._trusted_memories(session.user_id, workspace=session.workspace)
            if not account_id:
                memories = [item for item in memories if not item.get("account_id")]
            global_memories = self._trusted_memories(session.user_id, workspace=session.workspace)
            if account_id:
                by_id = {item["id"]: item for item in memories}
                for item in global_memories:
                    if not item.get("account_id"):
                        by_id[item["id"]] = item
                memories = list(by_id.values())
            if memories:
                lines.append("用户已确认记忆（冲突时以用户本轮说法为准）：")
                lines.extend(f"- {item['content']}" for item in memories[:15])
        except Exception:
            logger.exception("failed to build turn context for session %s", session.session_id)
        lines.append("</marketing-turn-context>")
        return "\n".join(lines)

    def _prefetch_required_evidence(self, task_id: str) -> dict[str, Any]:
        """Execute indispensable read-only evidence steps before model reasoning.

        The model may choose not to call a tool.  Account scope and degradation
        state are product invariants, so the product executor obtains them first
        and injects a compact, authoritative snapshot into every task turn.
        """
        task = self._store.get_task(task_id)
        plan = task.get("plan", [])
        required = {
            "marketing_read_context", "marketing_read_trends",
            "marketing_read_intelligence_report",
        }
        evidence: dict[str, Any] = {}

        for step in plan:
            name = step.get("tool_name")
            if name not in required or step.get("status") != "pending":
                continue
            spec = tool_by_name(name)
            if spec is None:
                continue
            arguments: dict[str, Any] = {}
            if task.get("account_id"):
                arguments["account_id"] = task["account_id"]
            step["status"] = "running"
            self._store.update_plan(task_id, plan)
            self._emit(
                task_id, "tool.started", tool_call_id=f"product:{step['id']}",
                tool=name, arguments=arguments, source="product_executor",
            )
            try:
                raw = spec.handler(arguments)
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                evidence[name] = parsed
                step["status"] = "completed"
                result = {"status": "ok", "data": parsed}
            except Exception as exc:
                logger.exception("product evidence prefetch failed for %s", name)
                evidence[name] = {"status": "error", "error": str(exc)}
                step["status"] = "skipped"
                result = {"status": "error", "error": str(exc), "retryable": False}
            self._store.update_plan(task_id, plan)
            self._emit(
                task_id, "tool.completed", tool_call_id=f"product:{step['id']}",
                tool=name, arguments=arguments, result=result,
                source="product_executor",
            )

        if evidence:
            checkpoint = self._build_checkpoint(task_id)
            self._store.update_task_progress(task_id, checkpoint=checkpoint)
            updated = self._store.get_task(task_id)
            self._emit(
                task_id, "plan.updated", plan=updated.get("plan", []),
                plan_version=updated.get("plan_version", 1), plan_total=len(plan),
            )
        return evidence

    @staticmethod
    def _format_authoritative_evidence(evidence: dict[str, Any]) -> list[str]:
        lines = ["本轮产品层权威证据（优先级高于历史对话）："]
        context = evidence.get("marketing_read_context")
        if isinstance(context, dict):
            scope = context.get("scope") or {}
            lines.append(f"- 当前账号范围：{scope.get('account_id') or '未指定'}")
            accounts = context.get("accounts") or []
            if accounts:
                account = accounts[0]
                snapshot = {
                    key: account.get(key)
                    for key in ("id", "platform", "label", "status", "stats")
                    if account.get(key) is not None
                }
                lines.append("- 当前账号明确字段：" + json.dumps(snapshot, ensure_ascii=False, default=str))
            else:
                lines.append("- 当前账号明确字段：未读取到账号快照。")
            industries = context.get("industries") or []
            lines.append(
                "- 全局监控行业（不是账号定位或标签）："
                + ("、".join(map(str, industries)) if industries else "未配置")
            )
            lines.append("- 未提供的账号字段一律视为未知：定位、标签、受众、内容数量、产品用户画像。")
        report = evidence.get("marketing_read_intelligence_report")
        if isinstance(report, dict):
            errors = report.get("errors") or []
            lines.append(
                f"- 最近巡检状态：{report.get('status', 'unknown')}；"
                f"错误/降级记录数：{len(errors)}。"
            )
        trends = evidence.get("marketing_read_trends")
        if isinstance(trends, dict):
            items = HermesAgentService._trend_items(trends)
            platforms = trends.get("platforms_succeeded") or sorted({
                str(item.get("source_platform")) for item in items if item.get("source_platform")
            })
            lines.append(
                f"- 热点缓存：{trends.get('total_deduped', len(items))} 条；"
                f"采集时间：{trends.get('cached_at') or trends.get('analyzed_at') or '未知'}；"
                f"成功平台：{json.dumps(platforms, ensure_ascii=False)}。"
            )
            if trends.get("source_errors") or trends.get("errors"):
                lines.append("- 热点源错误：" + json.dumps(
                    trends.get("source_errors") or trends.get("errors"), ensure_ascii=False,
                ))
            lines.append("- 可引用热点白名单（标题必须逐字来自这里）：")
            for item in items[:20]:
                lines.append("  - " + json.dumps({
                    key: item.get(key)
                    for key in ("title", "source_platform", "rank", "url", "collected_at", "category")
                    if item.get(key) not in (None, "")
                }, ensure_ascii=False, default=str))
        lines.append("输出时必须使用『已证实事实』『策略推断』『创作建议』标签；未知字段不得补写。")
        return lines

    @staticmethod
    def _trend_items(trends: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        categories = trends.get("categories") or {}
        ordered_groups = [
            values for name, values in categories.items() if name != "其他"
        ] + [trends.get("top_trends") or []]
        for group in ordered_groups:
            if not isinstance(group, list):
                continue
            for item in group:
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                key = (str(item.get("source_platform", "")), str(item["title"]))
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
        return items

    @staticmethod
    def _detect_evidence_violations(
        reply: str, evidence: dict[str, Any], account_id: str | None,
    ) -> list[str]:
        """Return concrete repair instructions for common evidence overclaims."""
        if not reply:
            return []
        violations: list[str] = []
        context = evidence.get("marketing_read_context")
        accounts = context.get("accounts", []) if isinstance(context, dict) else []
        # The account tool deliberately exposes no positioning/tag fields yet.
        # Therefore any such claim is unsupported even when prior chat said it.
        if account_id and accounts and re.search(
            r"账号(?:的)?(?:定位|标签)[^\n。；]{0,40}(?:AI|科技|教育|创业|产品)", reply, re.I,
        ):
            violations.append(
                "账号快照没有定位或标签字段；把相关表述改为『用户本轮指定的 AI 教育方向』，并明确账号正式定位尚未建立。"
            )
        expansive = [
            phrase for phrase in ("全网热议", "全网的", "全民关注", "自然流量大", "完美匹配")
            if phrase in reply
        ]
        if expansive:
            violations.append(
                "删除或降级这些无跨平台量化证据的扩大性判断："
                + "、".join(expansive)
                + "；如保留，只能标为策略推断。"
            )
        if re.search(r"(?:今天(?:是|正值)|正值).{0,16}(?:世界杯|淘汰赛日)", reply):
            violations.append(
                "热点标题不能证明今天的具体赛事日程；只能说同日热榜出现相关标题，赛事事实未单独核验。"
            )
        if ("新号阶段" in reply or "冷启动" in reply) and "策略推断" not in reply:
            violations.append(
                "『新号/冷启动』不是账号快照字段；若根据粉丝数提出，只能明确标注为策略推断。"
            )

        trends = evidence.get("marketing_read_trends")
        if isinstance(trends, dict):
            items = HermesAgentService._trend_items(trends)
            allowed_titles = {str(item.get("title", "")).strip() for item in items}
            allowed_urls = {str(item.get("url", "")).strip() for item in items if item.get("url")}
            allowed_platforms = {str(item.get("source_platform", "")).lower() for item in items}

            claimed_titles = re.findall(
                r"\|\s*\*{0,2}(?:原始标题|来源热点)\*{0,2}\s*\|\s*(.*?)\s*\|", reply,
            )
            invalid_titles = []
            for value in claimed_titles:
                title = re.sub(r"[*`]", "", value).strip()
                title = re.sub(r"\s*（[^）]*(?:热榜|第\d+位)[^）]*）\s*$", "", title).strip()
                if title and not any(title == allowed or title in allowed or allowed in title for allowed in allowed_titles):
                    invalid_titles.append(title)
            if invalid_titles:
                violations.append(
                    "这些『原始标题/来源热点』不在本轮热点证据白名单中："
                    + "、".join(invalid_titles[:5]) + "。"
                )

            platform_aliases = {
                "抖音": "douyin", "微博": "weibo", "知乎": "zhihu",
                "b站": "bilibili", "哔哩哔哩": "bilibili", "微信": "wechat",
            }
            source_rows = re.findall(r"\|\s*\*{0,2}来源平台\*{0,2}\s*\|\s*(.*?)\s*\|", reply)
            invalid_platforms = sorted({
                label for row in source_rows for label, code in platform_aliases.items()
                if label.lower() in row.lower() and code not in allowed_platforms
            })
            if invalid_platforms:
                violations.append(
                    "这些来源平台没有出现在本轮成功热点证据中："
                    + "、".join(invalid_platforms) + "。"
                )

            claimed_urls = set(re.findall(r"https?://[^\s)）|]+", reply))
            unsupported_urls = sorted(claimed_urls - allowed_urls)
            if unsupported_urls:
                violations.append("回答包含证据白名单之外的链接。")

            evidence_text = json.dumps(trends, ensure_ascii=False, default=str)
            unsupported_metrics = [
                match for match in re.findall(r"(?:约\s*)?\d+(?:\.\d+)?%|百万(?:级)?播放", reply)
                if match not in evidence_text
            ]
            if unsupported_metrics:
                violations.append(
                    "回答包含热点证据未提供的百分比或播放量级："
                    + "、".join(sorted(set(unsupported_metrics))) + "。"
                )
            if "采集时间推测" in reply or re.search(r"热点榜\s*`?[A-Z][A-Z0-9_]{5,}", reply):
                violations.append("采集时间和热点编号不得推测或自造。")
            if any(phrase in reply for phrase in ("最高权重", "高置信度", "置信度为**高**")):
                violations.append("算法权重和置信度没有量化证据，不得写成事实。")
        return violations

    @staticmethod
    def _build_grounding_failure_reply(evidence: dict[str, Any]) -> str:
        context = evidence.get("marketing_read_context") or {}
        accounts = context.get("accounts") or []
        account = accounts[0] if accounts else {}
        stats = account.get("stats") or {}
        trends = evidence.get("marketing_read_trends") or {}
        platforms = trends.get("platforms_succeeded") or []
        errors = trends.get("source_errors") or trends.get("errors") or {}
        return (
            "## 本轮未交付选题\n\n"
            "证据质量守门发现生成内容引用了本轮数据中不存在的热点标题、平台或指标，"
            "因此已拦截，未把它们作为真实结果交付。\n\n"
            "### 已证实事实\n\n"
            f"- 当前账号：{account.get('platform', '未知平台')} / {account.get('id', '未知 ID')}\n"
            f"- 指标快照：粉丝 {stats.get('followers', '未知')}，点赞 {stats.get('total_likes', '未知')}，播放 {stats.get('total_views', '未知')}\n"
            f"- 当前热点缓存：{trends.get('total_deduped', 0)} 条；成功平台：{json.dumps(platforms, ensure_ascii=False)}\n"
            f"- 失败数据源：{json.dumps(errors, ensure_ascii=False)}\n\n"
            "### 结论\n\n"
            "当前证据不足以可靠产出 3 个带真实来源的 AI 教育选题。系统选择返回空结果，"
            "而不是用推测标题补足数量。请稍后刷新数据源后重试。"
        )

    @staticmethod
    def _parse_plan_from_text(text: str) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for match in HermesAgentService._PLAN_RE.finditer(text):
            step_id = match.group(1)
            description = match.group(2).strip()
            if not description:
                continue
            tool_guess = HermesAgentService._guess_tool_for_step(description)
            steps.append({"id": step_id, "description": description, "tool_guess": tool_guess, "status": "pending"})
        return steps

    @staticmethod
    def _guess_tool_for_step(description: str) -> str | None:
        desc_lower = description.lower()
        for keywords, tool in HermesAgentService._TOOL_KEYWORDS:
            if any(kw in desc_lower for kw in keywords):
                return tool
        return None

    @staticmethod
    def _build_initial_plan(objective: str, account_id: str | None) -> list[dict[str, Any]]:
        """Create the product-visible execution plan before the model loop starts.

        This plan is deliberately small and capability-oriented.  It is not
        parsed from model prose, so UI/task recovery always shares one durable
        representation.
        """
        text = objective.lower()
        marketing_markers = (
            "热点", "趋势", "选题", "账号", "抖音", "营销", "内容", "脚本",
            "粉丝", "点赞", "播放", "行业", "发布", "复盘", "数据",
        )
        if not any(marker in text for marker in marketing_markers):
            return []

        steps: list[dict[str, Any]] = []
        next_id = 1

        def add(description: str, tool_name: str | None = None, *, kind: str = "tool") -> None:
            nonlocal next_id
            steps.append({
                "id": str(next_id),
                "description": description,
                "tool_name": tool_name,
                "kind": kind,
                "status": "pending",
            })
            next_id += 1

        if account_id or any(marker in text for marker in ("账号", "粉丝", "点赞", "播放", "抖音")):
            add("读取并核对当前账号的脱敏上下文", "marketing_read_context")

        if any(marker in text for marker in ("热点", "趋势", "选题", "行业")):
            add("检索带来源和时间的真实热点证据", "marketing_read_trends")
            add("核对数据源失败与降级状态", "marketing_read_intelligence_report")
        elif any(marker in text for marker in ("粉丝", "点赞", "播放", "账号数据")):
            add("读取账号最近指标快照", "marketing_read_accounts")

        add("整理输出并区分已证实事实、策略推断和创作建议", kind="synthesis")
        return steps

    def _finalize_plan(self, task_id: str) -> None:
        task = self._store.get_task(task_id)
        plan = task.get("plan", [])
        if not plan:
            return
        changed = False
        for step in plan:
            if step.get("kind") == "synthesis":
                if step.get("status") != "completed":
                    step["status"] = "completed"
                    changed = True
            elif step.get("status") in {"pending", "running"}:
                step["status"] = "skipped"
                changed = True
        if changed:
            self._store.update_plan(task_id, plan)
        checkpoint = self._build_checkpoint(task_id)
        self._store.update_task_progress(task_id, checkpoint=checkpoint)
        updated = self._store.get_task(task_id)
        self._emit(task_id, "plan.updated", plan=updated.get("plan", []),
                   plan_version=updated.get("plan_version", 1), plan_total=len(plan))

    def _capture_plan(self, session_id: str, objective: str) -> list[dict[str, Any]] | None:
        try:
            messages = self._session_db.get_messages_as_conversation(session_id)
            if not messages:
                return None
            for msg in reversed(messages):
                if not isinstance(msg, dict) or msg.get("role") != "assistant":
                    continue
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    content = " ".join(text_parts)
                if isinstance(content, str) and "计划" in content:
                    plan = self._parse_plan_from_text(content)
                    if plan:
                        logger.info("captured plan with %d steps for session %s", len(plan), session_id)
                        return plan
        except Exception:
            logger.exception("failed to capture plan from Hermes transcript %s", session_id)
        return None

    def _build_checkpoint(self, task_id: str) -> dict[str, Any]:
        """Build a deterministic checkpoint from current plan + event state."""
        task = self._store.get_task(task_id)
        plan = task.get("plan", [])
        completed = [s["id"] for s in plan if s.get("status") == "completed"]
        running = next((s for s in plan if s.get("status") == "running"), None)

        executed_effects: dict[str, dict[str, Any]] = {}
        try:
            for e in self._store.list_events_after(task_id, 0):
                if e["event_type"] == "effect.executed":
                    payload = e.get("payload", {})
                    effect_id = payload.get("effect_id", "")
                    if effect_id:
                        receipt = payload.get("receipt", {})
                        executed_effects[effect_id] = {
                            "capability": payload.get("capability", ""),
                            "receipt_status": receipt.get("status", "unknown") if isinstance(receipt, dict) else "unknown",
                        }
        except Exception:
            pass

        pending_approval_id = None
        try:
            for e in self._store.list_events_after(task_id, 0):
                if e["event_type"] == "approval.requested":
                    approval_id = e.get("payload", {}).get("approval_id")
                    if approval_id:
                        try:
                            approval = self._store.get_approval(approval_id)
                            if approval["status"] == "pending":
                                pending_approval_id = approval_id
                        except KeyError:
                            pass
        except Exception:
            pass

        pending = next((s for s in plan if s.get("status") in {"pending", "running"}), None)
        all_terminal = bool(plan) and all(
            s.get("status") in {"completed", "skipped"} for s in plan
        )
        return {
            "completed_steps": completed,
            "current_step": None if all_terminal else (
                running["id"] if running else (pending["id"] if pending else None)
            ),
            "executed_effects": executed_effects,
            "pending_approval_id": pending_approval_id,
        }

    def _emit(self, task_id: str, event_type: str, **payload) -> None:
        try:
            self._store.append_event(task_id, event_type, payload)
        except Exception:
            logger.exception("failed to persist event %s for %s", event_type, task_id)

    @staticmethod
    def _authorization_constraints(capability: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        stable_keys = {
            "marketing_trending_search": ("platform",),
            "marketing_session_login": ("platform",),
            "marketing_accounts_sync": ("platform", "username"),
        }.get(capability, ())
        supplied = arguments or {}
        constraints = {key: supplied[key] for key in stable_keys if key in supplied}
        if supplied.get("account_id"):
            constraints["account_id"] = supplied["account_id"]
        return constraints

    def grant_authorization(
        self, user_id: str, capability: str, scope: str,
        session_id: str | None = None, arguments: dict[str, Any] | None = None,
    ) -> dict:
        constraints = self._authorization_constraints(capability, arguments)
        if scope == "permanent":
            return self._store.grant_authorization(user_id, capability, constraints)
        if scope == "session" and session_id:
            self._session_auths.setdefault(session_id, {})[capability] = constraints
            return {"capability": capability, "scope": "session", "session_id": session_id, "constraints": constraints}
        return {"capability": capability, "scope": "once"}

    def revoke_authorization(self, user_id: str, capability: str, session_id: str | None = None) -> dict:
        try:
            self._store.revoke_authorization(user_id, capability)
        except KeyError:
            pass
        if session_id:
            self._session_auths.get(session_id, {}).pop(capability, None)
        return {"revoked": capability}

    def get_store(self) -> AgentCoreStore:
        return self._store

    @staticmethod
    def _summarize_receipt(receipt: dict) -> str:
        if "items" in receipt:
            return f"搜索到 {len(receipt.get('items', []))} 条内容，关键词「{receipt.get('keyword', '')}」"
        if "followers" in receipt or "total_likes" in receipt:
            parts = []
            for key, label in [("followers", "粉丝"), ("total_likes", "获赞"), ("total_views", "播放")]:
                val = receipt.get(key)
                if val is not None:
                    parts.append(f"{label} {val}")
            return f"账号同步完成：{', '.join(parts)}"
        if receipt.get("status") == "logged_in":
            return f"平台 {receipt.get('platform', '')} 登录成功"
        text = json.dumps(receipt, ensure_ascii=False)
        return text[:500]

    def shutdown(self) -> None:
        with self._lock:
            task_ids = list(self._task_agents)
            threads = list(self._task_threads.values())
        for task_id in task_ids:
            try:
                self._stop_task(task_id, TaskStatus.PAUSED, "runtime shutdown")
            except Exception:
                pass
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=5)
