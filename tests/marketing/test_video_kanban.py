from __future__ import annotations

import base64
import json
import sqlite3
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agent.account_registry import AccountRegistry
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.drafts import DraftBoxRepository
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.material_sourcing import MaterialSourcingRepository
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.operating_entities import OperatingEntityRepository
from agent.marketing.domains.video_kanban import (
    PAID_VIDEO_EXECUTION_ARMED,
    VIDEO_EXECUTION_VERSION,
    VideoKanbanExecutionRepository,
    probe_doubao_video_model,
)
from agent.marketing.intelligence.store import OperatingLoopRepository
from hermes_state import SessionDB
from tools.marketing_tools import _official_video_repository
from toolsets import resolve_toolset


def _paths(tmp_path) -> MarketingDataPaths:
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=tmp_path / "config",
        agent_db=tmp_path / "state.db",
    )


def _scope(paths: MarketingDataPaths) -> tuple[str, str]:
    owner = SessionDB(db_path=paths.agent_db)
    account = AccountRegistry(owner).register_pending(platform="douyin")
    owner.close()
    entity = OperatingEntityRepository(paths).ensure_for_account(
        user_id="default", account_id=account["id"]
    )
    return entity["id"], account["id"]


def _video_plan(paths: MarketingDataPaths, account_id: str, *, topic: str) -> str:
    return ContentAssetRepository(paths).save_production_plan(
        user_id="default",
        account_id=account_id,
        plan={
            "status": "planned",
            "kind": "faceless_video",
            "objective": topic,
            "target_platforms": ["douyin"],
            "constraints": {},
            "audience_model": {"target_audience": "AI 创业者"},
        },
    )["plan_id"]


def _approve_director_treatment(
    repository: VideoKanbanExecutionRepository,
    execution: dict,
    *,
    evidence_id: str,
    evidence_quote: str,
) -> dict:
    workspace = Path(execution["workspace_path"])
    projection = execution["execution"]
    director_context = json.loads(
        (workspace / "director-context.json").read_text(encoding="utf-8")
    )
    delivery = director_context["delivery"]
    minimum_shots = int(projection["minimum_shots"])
    target_duration = float(delivery["target_duration_seconds"])
    shot_duration = target_duration / minimum_shots
    shots = []
    for index in range(minimum_shots):
        shot_id = f"shot_{index + 1:02d}"
        shots.append(
            {
                "id": shot_id,
                "purpose": "用可验证画面推进论证",
                "duration": shot_duration,
                "narration_text": f"这是第 {index + 1} 个有证据的论证节拍。",
                "visual_subject": "GPU server racks and AI builders",
                "visual_query": "GPU server racks AI builders documentary",
                "scene": "data center",
                "style": "documentary",
                "frame": "medium wide",
                "camera": "slow push in",
                "blocking": "subject remains in the center safe area",
                "on_screen_text": f"证据 {index + 1}",
                "composition_strategy": "inset_card",
                "negative_conditions": ["unrelated generic office"],
                "claim_evidence_refs": [evidence_id],
                "claim_evidence_quotes": {evidence_id: evidence_quote},
                "continuity_anchors": ["neutral warm palette"],
                "pass_criteria": ["画面主体与当前旁白直接相关"],
                "metric_hypothesis": {
                    "intended_response": "继续观看",
                    "observable_metric": "shot_retention",
                    "failure_signal": "drop_off",
                    "repair": "replace the visual proof",
                },
            }
        )
    knowledge_ids = [
        str(item["id"])
        for rows in (director_context.get("knowledge_bases") or {}).values()
        for item in rows
        if isinstance(item, dict) and item.get("id")
    ]
    graph_ids = [
        str(item["id"])
        for item in [
            *((director_context.get("benchmark_operating_graph") or {}).get("nodes") or []),
            *((director_context.get("benchmark_operating_graph") or {}).get("observations") or []),
        ]
        if isinstance(item, dict) and item.get("id")
    ]
    human_projection = director_context.get("human_observer_projection") or {}
    human_ids = [
        str(item["id"])
        for item in [
            *(human_projection.get("interpretations") or []),
            *(human_projection.get("model_revisions") or []),
        ]
        if isinstance(item, dict) and item.get("id")
    ]
    treatment = {
        "platform": execution["platform"],
        "thesis": "先区分资本泡沫和长期技术价值",
        "voiceover_script": "。".join(shot["narration_text"] for shot in shots),
        "hook": "AI 真的是泡沫，还是我们混淆了两件事？",
        "hook_hypothesis": {
            "first_three_seconds": "AI 真的是泡沫，还是我们混淆了两件事？",
            "tension": "估值泡沫不等于技术没有价值",
        },
        "target_duration": target_duration,
        "aspect_ratio": delivery["aspect_ratio"],
        "pacing": "evidence-led fast documentary",
        "caption_style": "single-line safe-area captions",
        "cta": "关注后续数据复盘",
        "sound_strategy": {
            "voice_style": "calm analytical",
            "music_role": "low tension bed",
            "sfx_cues": ["hook impact"],
        },
        "beat_sheet": [
            {"shot_id": shot["id"], "purpose": shot["purpose"]} for shot in shots
        ],
        "claim_evidence_map": [
            {"claim": "可验证的 AI 市场判断", "evidence_refs": [evidence_id]}
        ],
        "continuity_bible": {"palette": "neutral warm"},
        "shot_list": shots,
    }
    contract = {
        "contract": "marketing.video.director.v1",
        "execution_id": execution["id"],
        "platform": execution["platform"],
        "topic": director_context["topic"],
        "production_contract": {
            "objective": "完成有证据的短视频",
            "audience_state": "对 AI 泡沫论困惑",
            "viewer_tension": "资本价格与技术价值混在一起",
            "promise": "给出可操作的区分框架",
            "proof": [evidence_id],
            "placement": execution["platform"],
            "action": "继续关注复盘",
            "constraints": ["不得虚构"],
            "primary_metric": "completion_rate",
            "guardrails": ["exact evidence quotes"],
        },
        "knowledge_basis": {
            "knowledge_entry_ids": knowledge_ids,
            "benchmark_graph_ids": graph_ids,
            "uses": [
                {"source_id": item, "decision": "constrained the argument or visual plan"}
                for item in [*knowledge_ids, *graph_ids]
            ],
        },
        "human_observer_basis": {
            "authority": "read_only_no_score_or_writeback",
            "projection_ids": human_ids,
            "uses": [
                {"source_id": item, "decision": "formed a falsifiable audience question"}
                for item in human_ids
            ],
            "cold_start": not human_ids,
        },
        "treatment": treatment,
        "grounding_review": {
            "unsupported_claims": [],
            "stance_conflicts": [],
            "invented_personal_proof": [],
            "invented_offers": [],
            "go": True,
        },
        "measurement_plan": {
            "primary_metric": "completion_rate",
            "shot_hypotheses": [shot["metric_hypothesis"] for shot in shots],
        },
    }
    (workspace / "director-contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (workspace / "script.md").write_text(treatment["voiceover_script"], encoding="utf-8")
    (workspace / "narration.json").write_text(
        json.dumps({"segments": shots}, ensure_ascii=False), encoding="utf-8"
    )
    (workspace / "storyboard.json").write_text(
        json.dumps({"shots": shots}, ensure_ascii=False), encoding="utf-8"
    )
    (workspace / "visual-spec.md").write_text(
        "# Visual spec\n\nDocumentary evidence, safe-area captions.\n", encoding="utf-8"
    )
    receipt = repository.preflight_treatment(
        execution_id=execution["id"],
        actor_profile="marketing-video-director",
        tenant=execution["tenant"],
        kanban_task_id="task-director",
    )
    assert receipt["preflight_decision"]["go"] is True
    return receipt


class _Response:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_probe_selects_live_seed_21_pro_and_requires_function_call(monkeypatch):
    import requests

    observed = {}
    probed_models = []

    monkeypatch.setattr("hermes_cli.config.get_env_value", lambda key: "local-secret")
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _Response(
            {
                "data": [
                    {"id": "doubao-seed-2-0-mini-260428"},
                    {"id": "doubao-seed-2-0-lite-260428"},
                    {"id": "doubao-seed-2-1-pro-260628"},
                ]
            }
        ),
    )
    def post(*args, **kwargs):
        observed.update(kwargs.get("json") or {})
        probed_models.append((kwargs.get("json") or {}).get("model"))
        return _Response(
            {
                "output": [
                    {"type": "function_call", "name": "video_runtime_ready"}
                ],
                "usage": {"input_tokens": 8, "output_tokens": 2},
            }
        )

    monkeypatch.setattr(requests, "post", post)

    result = probe_doubao_video_model()

    assert result["model"] == "doubao-seed-2-1-pro-260628"
    assert result["execution_model"] == "doubao-seed-2-0-lite-260428"
    assert result["probe"] == "function_call_ok"
    assert probed_models == [
        "doubao-seed-2-1-pro-260628",
        "doubao-seed-2-0-lite-260428",
    ]
    assert observed["tool_choice"] == {
        "type": "function",
        "name": "video_runtime_ready",
    }
    assert "local-secret" not in json.dumps(result)


def test_probe_blocks_instead_of_falling_back_when_seed_21_pro_is_unavailable(
    monkeypatch,
):
    import requests

    monkeypatch.setattr("hermes_cli.config.get_env_value", lambda key: "local-secret")
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _Response(
            {"data": [{"id": "doubao-seed-2-0-mini-260428"}]}
        ),
    )

    with pytest.raises(RuntimeError, match="no Seed 2.1 Pro"):
        probe_doubao_video_model()


def test_paid_video_execution_is_hard_stopped_outside_injected_tests(tmp_path):
    assert PAID_VIDEO_EXECUTION_ARMED is False
    paths = _paths(tmp_path)
    entity_id, account_id = _scope(paths)
    with pytest.raises(RuntimeError, match="paid_video_execution_emergency_stopped"):
        VideoKanbanExecutionRepository(paths).submit(
            user_id="default",
            entity_id=entity_id,
            account_id=account_id,
            candidate_id="candidate-cost-stop",
            plan_id="plan-cost-stop",
            preflight_id="preflight-cost-stop",
            platform="douyin",
            topic="cost stop",
            context={"evidence_refs": ["evidence-cost-stop"]},
        )


def test_submit_bootstraps_the_official_seven_profile_kanban(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    entity_id, account_id = _scope(paths)
    plan_id = _video_plan(paths, account_id, topic="当前的 AI 是泡沫吗？")
    evidence_quote = "Verified evidence for the AI bubble director contract."

    def runner(command, *, cwd):
        if command[0] == sys.executable:
            return subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
            )
        setup = Path(command[1])
        workspace = setup.parent
        (workspace / ".kanban-root.json").write_text(
            json.dumps({"id": "task-official-root"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    repository = VideoKanbanExecutionRepository(paths)
    execution = repository.submit(
        user_id="default",
        entity_id=entity_id,
        account_id=account_id,
        candidate_id="candidate-1",
        plan_id=plan_id,
        preflight_id="preflight-1",
        platform="douyin",
        topic="当前的 AI 是泡沫吗？",
        context={
            "evidence_refs": ["evidence-1"],
            "evidence_pack": [
                {"id": "evidence-1", "excerpt": evidence_quote}
            ],
            "knowledge_context": {
                "platform": [
                    {
                        "id": "knowledge-platform-1",
                        "statement": "抖音开头应尽快兑现信息承诺。",
                    }
                ],
                "market": [],
                "account": [],
                "content": [],
                "authority_order": ["account", "platform", "market", "content"],
            },
            "account_context": {
                "target_audience": "AI 创业者",
                "lifecycle": {
                    "benchmark_operating_graph": {
                        "contract": "marketing.benchmark-operating-graph.v1",
                        "nodes": [{"id": "benchmark-node-1", "role": "format_peer"}],
                        "observations": [
                            {"id": "benchmark-observation-1", "metric": "hook"}
                        ],
                        "authority": "evidence_backed_account_strategy_read_projection",
                    }
                },
            },
            "human_observer_projection": {
                "contract": "human-observer-read-projection-v1",
                "namespace": "global",
                "interpretations": [
                    {"id": "human-interpretation-1", "status": "candidate"}
                ],
                "model_revisions": [],
                "authority": "read_only_no_product_writeback",
            },
            "target_duration": 60,
        },
        command_runner=runner,
        model_probe=lambda: {
            "provider": "volcengine_ark",
            "model": "doubao-seed-2-1-pro-260628",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_mode": "codex_responses",
            "probe": "function_call_ok",
        },
    )

    workspace = tmp_path / "marketing-video-kanban" / execution["id"]
    plan = json.loads((workspace / "plan.json").read_text(encoding="utf-8"))
    manifest_contract = json.loads(
        (workspace / "MANIFEST_CONTRACT.json").read_text(encoding="utf-8")
    )
    team = (workspace / "TEAM.md").read_text(encoding="utf-8")
    setup = (workspace / "setup.sh").read_text(encoding="utf-8")
    assert execution["contract_version"] == VIDEO_EXECUTION_VERSION
    assert execution["status"] == "queued"
    assert execution["root_task_id"] == "task-official-root"
    assert execution["execution"]["evidence_refs"] == ["evidence-1"]
    assert execution["execution"]["production_revision"] == "initial"
    assert set(execution["execution"]["input_integrity"]) == {
        "plan.json",
        "brief.md",
        "TEAM.md",
        "marketing-context.json",
        "director-context.json",
        "PRODUCTION_RULES.md",
        "MANIFEST_CONTRACT.json",
        "taste/brand-guide.md",
        "taste/emotional-dna.md",
    }
    assert manifest_contract["contract"] == VIDEO_EXECUTION_VERSION
    assert manifest_contract["finalize"]["destination"] == "draft_box"
    assert len(plan["team"]) == 7
    assert {member["profile"] for member in plan["team"]} >= {
        "marketing-video-coordinator",
        "marketing-video-director",
        "marketing-video-material-scout",
        "marketing-video-voice",
        "marketing-video-renderer",
        "marketing-video-editor",
        "marketing-video-reviewer",
    }
    assert "marketing-video-dp" not in setup
    assert "marketing-video-renderer — render all locked storyboard scenes" in team
    assert '--assignee "marketing-video-coordinator"' in setup
    assert 'hermes kanban --board "$BOARD" create' in setup
    assert '\nhermes kanban create ' not in setup
    assert "doubao-seed-2-1-pro-260628" in setup
    assert 'cfg.setdefault("platform_toolsets", {})["cli"] = toolsets' in setup
    assert 'cfg.setdefault("agent", {})["reasoning_effort"] = "none"' in setup
    assert "HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS=300" in setup
    assert 'chmod a-w \\\n    "$WORKSPACE/plan.json"' in setup
    assert "MARKETING_CANONICAL_AGENT_DB" in setup
    assert "MARKETING_OS_AGENT_DB=" in setup
    assert '"max_output_tokens": int(provider.get' not in setup
    assert resolve_toolset("marketing_video_finalize") == [
        "marketing_video_finalize"
    ]
    material_scout = next(
        member
        for member in plan["team"]
        if member["profile"] == "marketing-video-material-scout"
    )
    assert material_scout["model"] == "doubao-seed-2-0-lite-260428"
    assert material_scout["model_tier"] == "execution_lite"
    assert next(
        member
        for member in plan["team"]
        if member["profile"] == "marketing-video-director"
    )["model"] == "doubao-seed-2-1-pro-260628"
    assert next(
        member
        for member in plan["team"]
        if member["profile"] == "marketing-video-director"
    )["skills"] == ["marketing-super-director"]
    assert resolve_toolset("marketing_video_direction") == [
        "marketing_video_treatment_preflight"
    ]
    assert "marketing_video_materials" in material_scout["toolsets"]
    assert set(resolve_toolset("marketing_video_materials")) == {
        "marketing_video_material_search",
        "marketing_video_material_register",
        "marketing_video_material_inspect",
        "marketing_video_material_assess",
        "marketing_video_material_clip",
        "marketing_video_material_freeze",
    }
    assert "local-secret" not in setup
    director_context = json.loads(
        (workspace / "director-context.json").read_text(encoding="utf-8")
    )
    assert director_context["knowledge_bases"]["platform"][0]["id"] == (
        "knowledge-platform-1"
    )
    assert director_context["benchmark_operating_graph"]["observations"][0][
        "id"
    ] == "benchmark-observation-1"
    assert director_context["human_observer_projection"]["interpretations"][0][
        "id"
    ] == "human-interpretation-1"

    observed = {}

    def material_search(_self, **kwargs):
        observed.update(kwargs)
        return {"status": "completed", "candidates": []}

    monkeypatch.setattr(MaterialSourcingRepository, "search", material_search)
    with pytest.raises(PermissionError, match="treatment preflight"):
        repository.search_materials(
            execution_id=execution["id"],
            shot_id="shot-01",
            query="must not search before the script contract",
            actor_profile="marketing-video-material-scout",
            tenant=execution["tenant"],
            kanban_task_id="material-task-before-treatment",
        )
    _approve_director_treatment(
        repository,
        execution,
        evidence_id="evidence-1",
        evidence_quote=evidence_quote,
    )
    director_contract = json.loads(
        (workspace / "director-contract.json").read_text(encoding="utf-8")
    )
    ignored_knowledge = json.loads(json.dumps(director_contract))
    ignored_knowledge["knowledge_basis"]["knowledge_entry_ids"] = []
    with pytest.raises(ValueError, match="ignored available governed knowledge"):
        repository._validate_director_contract(
            execution=execution,
            workspace=workspace,
            contract=ignored_knowledge,
            director_context=director_context,
        )
    searched = repository.search_materials(
        execution_id=execution["id"],
        shot_id="shot-01",
        query="solo founder working at night portrait documentary",
        media_type="image",
        actor_profile="marketing-video-material-scout",
        tenant=execution["tenant"],
        kanban_task_id="material-task-1",
    )
    assert searched["cost_cny"] == 0
    assert searched["shot_id"] == "shot-01"
    assert observed["user_id"] == "default"
    assert observed["account_id"] == account_id
    assert observed["request_ref"].startswith(f"{execution['id']}:shot-01:")
    with pytest.raises(PermissionError, match="marketing-video-material-scout"):
        repository.search_materials(
            execution_id=execution["id"],
            shot_id="shot-01",
            query="forbidden cross-role call",
            actor_profile="marketing-video-editor",
            tenant=execution["tenant"],
            kanban_task_id="editor-task-1",
        )
    monkeypatch.setenv("HERMES_KANBAN_WORKSPACE", str(workspace))
    assert _official_video_repository().paths.agent_db == paths.agent_db

    brand_guide = workspace / "taste/brand-guide.md"
    assert "locked system input" in brand_guide.read_text(encoding="utf-8")
    brand_guide.write_text("tampered by a worker\n", encoding="utf-8")
    with pytest.raises(ValueError, match="locked video inputs were modified"):
        repository.search_materials(
            execution_id=execution["id"],
            shot_id="shot-02",
            query="tampered execution must stop",
            actor_profile="marketing-video-material-scout",
            tenant=execution["tenant"],
            kanban_task_id="material-task-2",
        )

    revised = VideoKanbanExecutionRepository(paths).submit(
        user_id="default",
        entity_id=entity_id,
        account_id=account_id,
        candidate_id="candidate-1",
        plan_id=plan_id,
        preflight_id="preflight-1",
        platform="douyin",
        topic="当前的 AI 是泡沫吗？",
        context={
            "evidence_refs": ["evidence-1"],
            "target_duration": 60,
            "production_revision": 2,
        },
        command_runner=runner,
        model_probe=lambda: {
            "provider": "volcengine_ark",
            "model": "doubao-seed-2-1-pro-260628",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_mode": "codex_responses",
            "probe": "function_call_ok",
        },
    )
    assert revised["id"] != execution["id"]
    assert revised["tenant"] != execution["tenant"]
    assert revised["execution"]["production_revision"] == "2"


def test_material_freeze_requires_a_passing_grounded_scout_inspection(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    entity_id, account_id = _scope(paths)
    plan_id = _video_plan(paths, account_id, topic="AI 算力军备竞赛")
    evidence_quote = "Verified evidence for the GPU server material test."

    def runner(command, *, cwd):
        if command[0] == sys.executable:
            return subprocess.run(
                command, cwd=cwd, check=False, capture_output=True, text=True
            )
        workspace = Path(command[1]).parent
        (workspace / ".kanban-root.json").write_text(
            json.dumps({"id": "task-material-inspection"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    repository = VideoKanbanExecutionRepository(paths)
    execution = repository.submit(
        user_id="default",
        entity_id=entity_id,
        account_id=account_id,
        candidate_id="candidate-material-inspection",
        plan_id=plan_id,
        preflight_id="preflight-material-inspection",
        platform="douyin",
        topic="AI 算力军备竞赛",
        context={
            "evidence_refs": ["evidence-1"],
            "evidence_pack": [
                {"id": "evidence-1", "excerpt": evidence_quote}
            ],
        },
        command_runner=runner,
        model_probe=lambda: {
            "provider": "volcengine_ark",
            "model": "doubao-seed-2-1-pro-260628",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_mode": "codex_responses",
            "probe": "function_call_ok",
        },
    )
    source = tmp_path / "gpu-server-rack.png"
    source.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    MediaAssetRepository(paths).import_generated_file(
        user_id="default",
        account_id=account_id,
        name="GPU server rack close-up",
        media_type="image",
        role="broll",
        path=source,
        mime_type="image/png",
        provider="owned-test",
        provider_asset_id="gpu-server-rack-1",
        source_type="user_upload",
        rights_status="user_confirmed",
    )
    _approve_director_treatment(
        repository,
        execution,
        evidence_id="evidence-1",
        evidence_quote=evidence_quote,
    )
    search = repository.search_materials(
        execution_id=execution["id"],
        shot_id="shot_01",
        query="GPU server rack",
        actor_profile="marketing-video-material-scout",
        tenant=execution["tenant"],
        kanban_task_id="task-material-scout",
    )
    candidate_id = search["search"]["candidates"][0]["id"]

    monkeypatch.setattr(
        MaterialSourcingRepository,
        "prepare_video_analysis",
        lambda *_args, **_kwargs: {
            "candidate_id": candidate_id,
            "frames": [{"path": "/tmp/frame.jpg", "timestamp_seconds": 1}],
            "native_captions_only": True,
            "whisper_used": False,
            "cost_cny": 0,
        },
    )
    inspection = repository.inspect_material(
        execution_id=execution["id"],
        shot_id="shot_01",
        candidate_id=candidate_id,
        narration_text="大厂正在烧钱争夺 AI 算力。",
        visual_subject="Rows of illuminated GPU server racks",
        composition_strategy="full_bleed",
        actor_profile="marketing-video-material-scout",
        tenant=execution["tenant"],
        kanban_task_id="task-material-scout",
    )
    assert inspection["passed"] is False
    assert inspection["model"] == "local_watch_pending"
    assert inspection["receipt"]["cost_cny"] == 0
    inspection = repository.assess_material(
        execution_id=execution["id"],
        inspection_id=inspection["id"],
        relevance_score=0.86,
        semantic_evidence="Visible rows of illuminated GPU server racks.",
        observed_subjects=["GPU racks"],
        source_in=0,
        source_out=1,
        actor_profile="marketing-video-material-scout",
        tenant=execution["tenant"],
        kanban_task_id="task-material-scout",
    )
    assert inspection["passed"] is True
    assert inspection["score"] == 0.86
    assert inspection["receipt"]["provider"] == "local_watch"

    with pytest.raises((KeyError, ValueError)):
        repository.freeze_material(
            execution_id=execution["id"],
            shot_id="shot_01",
            candidate_id=candidate_id,
            inspection_id="missing-inspection",
            license_verified=True,
            actor_profile="marketing-video-material-scout",
            tenant=execution["tenant"],
            kanban_task_id="task-material-scout",
        )
    frozen = repository.freeze_material(
        execution_id=execution["id"],
        shot_id="shot_01",
        candidate_id=candidate_id,
        inspection_id=inspection["id"],
        license_verified=True,
        actor_profile="marketing-video-material-scout",
        tenant=execution["tenant"],
        kanban_task_id="task-material-scout",
    )
    assert frozen["receipt"]["inspection_id"] == inspection["id"]
    assert frozen["receipt"]["semantic_relevance"] == 0.86


def test_blocked_official_execution_is_managed_in_draft_box(tmp_path):
    paths = _paths(tmp_path)
    entity_id, account_id = _scope(paths)

    def runner(command, *, cwd):
        if command[0] == sys.executable:
            return subprocess.run(
                command, cwd=cwd, check=False, capture_output=True, text=True
            )
        workspace = Path(command[1]).parent
        (workspace / ".kanban-root.json").write_text(
            json.dumps({"id": "task-draft-box"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    repository = VideoKanbanExecutionRepository(paths)
    execution = repository.submit(
        user_id="default",
        entity_id=entity_id,
        account_id=account_id,
        candidate_id="candidate-draft-box",
        plan_id="plan-draft-box",
        preflight_id="preflight-draft-box",
        platform="douyin",
        topic="被阻断的视频任务",
        context={"evidence_refs": ["evidence-draft-box"]},
        command_runner=runner,
        model_probe=lambda: {
            "provider": "volcengine_ark",
            "model": "doubao-seed-2-1-pro-260628",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_mode": "codex_responses",
            "probe": "function_call_ok",
        },
    )
    repository._set_failure(execution["id"], RuntimeError("free material unavailable"))

    draft_box = DraftBoxRepository(paths)
    item = next(
        entry
        for entry in draft_box.list(
            user_id="default", account_id=account_id
        )["items"]
        if entry["id"] == execution["id"]
    )
    assert item["object_type"] == "video_execution"
    assert item["workflow_stage"] == "production_blocked"
    assert item["can_archive"] is True

    archived = draft_box.archive(
        object_type="video_execution",
        object_id=execution["id"],
        user_id="default",
        account_id=account_id,
        confirmed=True,
    )
    assert archived["item"]["status"] == "archived"
    restored = draft_box.restore(
        object_type="video_execution",
        object_id=execution["id"],
        user_id="default",
        account_id=account_id,
    )
    assert restored["item"]["status"] == "blocked"


def test_draft_box_reconciles_a_terminal_official_kanban_block(tmp_path, monkeypatch):
    from hermes_cli import kanban_db as kb

    paths = _paths(tmp_path)
    entity_id, account_id = _scope(paths)
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "kanban.db"))

    def runner(command, *, cwd):
        if command[0] == sys.executable:
            return subprocess.run(
                command, cwd=cwd, check=False, capture_output=True, text=True
            )
        workspace = Path(command[1]).parent
        plan = json.loads((workspace / "plan.json").read_text(encoding="utf-8"))
        conn = kb.connect()
        try:
            root_task_id = kb.create_task(
                conn,
                title="blocked official video",
                assignee="marketing-video-director",
                tenant=plan["tenant"],
                workspace_kind="dir",
                workspace_path=str(workspace),
                initial_status="blocked",
            )
        finally:
            conn.close()
        (workspace / ".kanban-root.json").write_text(
            json.dumps({"id": root_task_id}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    execution = VideoKanbanExecutionRepository(paths).submit(
        user_id="default",
        entity_id=entity_id,
        account_id=account_id,
        candidate_id="candidate-kanban-block",
        plan_id="plan-kanban-block",
        preflight_id="preflight-kanban-block",
        platform="douyin",
        topic="官方任务阻断投影",
        context={"evidence_refs": ["evidence-kanban-block"]},
        command_runner=runner,
        model_probe=lambda: {
            "provider": "volcengine_ark",
            "model": "doubao-seed-2-1-pro-260628",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_mode": "codex_responses",
            "probe": "function_call_ok",
        },
    )

    assert execution["status"] == "queued"
    item = next(
        entry
        for entry in DraftBoxRepository(paths).list(
            user_id="default", account_id=account_id
        )["items"]
        if entry["id"] == execution["id"]
    )
    assert item["workflow_stage"] == "production_blocked"
    assert item["failure_code"] == "official_kanban_blocked"


def test_delivery_gate_enforces_semantics_diversity_rights_and_evidence():
    execution = {
        "id": "video-execution-1",
        "execution": {"evidence_refs": ["evidence-1"]},
        "model": {"model": "doubao-seed-2-1-pro-260628"},
        "budget": {
            "execution_model": "doubao-seed-2-0-lite-260428",
            "max_pro_model_calls": 16,
            "max_lite_execution_calls": 16,
            "max_tts_characters": 6_000,
        },
    }
    scenes = [
        {
            "id": f"scene-{index}",
            "narration_segment": {"text": f"旁白 {index}"},
            "claim_evidence_refs": ["evidence-1"],
            "claim_evidence_quotes": {"evidence-1": "locked evidence quote"},
            "start_seconds": float(index - 1),
            "end_seconds": float(index),
            "source_in": 0.0,
            "source_out": 1.0,
            "composition_strategy": "inset_card",
            "review": {"passed": True},
        }
        for index in range(1, 5)
    ]
    manifests = {
        "delivery": {
            "execution_id": "video-execution-1",
            "evidence_refs": ["evidence-1"],
            "paid_material_generation_calls": [],
            "scenes": scenes,
            "model_receipts": [
                {
                    "provider": "volcengine_ark",
                    "model": "doubao-seed-2-1-pro-260628",
                    "usage": {"input_tokens": 10},
                    "estimated_cost_cny": 0.01,
                },
                {
                    "provider": "volcengine_ark",
                    "model": "doubao-seed-2-0-lite-260428",
                    "usage": {"input_tokens": 10},
                    "estimated_cost_cny": 0.001,
                },
            ],
            "tool_receipts": [{"tool": "video-use", "status": "ok"}],
            "narration": {
                "receipts": [
                    {
                        "provider": "volcengine",
                        "provider_task_id": "tts-1",
                        "characters": 16,
                        "estimated_cost_cny": 0.01,
                    }
                ]
            },
        },
        "review": {
            "passed": True,
            "semantic_review_pass": True,
            "caption_safe_area_pass": True,
            "audio_sync_pass": True,
            "composition_pass": True,
            "rights_pass": True,
            "repair_rounds": 2,
        },
        "materials": {
            "receipts": [
                {"provider": "wikimedia", "status": "frozen", "cost_cny": 0}
            ],
            "shots": [
                {"asset_id": "a", "semantic_relevance": 0.9, "semantic_evidence": "AI server"},
                {"asset_id": "b", "semantic_relevance": 0.8, "semantic_evidence": "market chart"},
                {"asset_id": "a", "semantic_relevance": 0.75, "semantic_evidence": "AI server detail"},
                {"asset_id": "c", "semantic_relevance": 0.76, "semantic_evidence": "working user"},
            ]
        },
        "rights": {
            "assets": [
                {"asset_id": key, "allowed_for_use": True, "license": "CC0", "source_url": f"https://example.com/{key}"}
                for key in ("a", "b", "c")
            ]
        },
    }

    VideoKanbanExecutionRepository._validate_delivery(execution, manifests)
    manifests["materials"]["shots"][1] = {
        "material_kind": "original_renderer",
        "asset_id": "original_renderer:scene-2",
        "render_artifact_path": "scenes/scene-2/clip.mp4",
        "semantic_relevance": 1.0,
        "semantic_evidence": "Original chart animation follows the locked scene contract.",
    }
    manifests["materials"]["receipts"].append({
        "provider": "official_renderer",
        "status": "rendered",
        "cost_cny": 0,
        "artifact_path": "scenes/scene-2/clip.mp4",
    })
    manifests["rights"]["assets"].append({
        "asset_id": "original_renderer:scene-2",
        "allowed_for_use": True,
        "license": "original_work",
        "source_path": "scenes/scene-2/clip.mp4",
    })
    VideoKanbanExecutionRepository._validate_delivery(execution, manifests)
    manifests["delivery"]["paid_material_generation_calls"] = ["forbidden"]
    with pytest.raises(ValueError, match="paid material generation"):
        VideoKanbanExecutionRepository._validate_delivery(execution, manifests)
    manifests["delivery"]["paid_material_generation_calls"] = []
    scenes[0]["claim_evidence_refs"] = ["evidence-outside-brief"]
    with pytest.raises(ValueError, match="claim evidence is outside"):
        VideoKanbanExecutionRepository._validate_delivery(execution, manifests)


def test_original_renderer_material_requires_a_real_rendered_artifact(
    tmp_path: Path,
):
    repository = VideoKanbanExecutionRepository(_paths(tmp_path / "data"))
    workspace = tmp_path / "workspace"
    clip = workspace / "scenes" / "scene-2" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"rendered-scene")
    execution = {
        "id": "video-execution-original",
        "workspace_path": str(workspace),
        "budget": {"material_screening_model": "doubao-seed-2-0-mini-260428"},
    }
    materials = {
        "shots": [{
            "shot_id": "scene-2",
            "material_kind": "original_renderer",
            "asset_id": "original_renderer:scene-2",
            "render_artifact_path": "scenes/scene-2/clip.mp4",
            "semantic_relevance": 1.0,
            "semantic_evidence": "Original chart animation follows the locked scene contract.",
        }]
    }

    repository._validate_material_inspections(execution, materials)
    clip.unlink()
    with pytest.raises(ValueError, match="no rendered MP4 artifact"):
        repository._validate_material_inspections(execution, materials)


def test_scene_claim_quotes_must_be_exact_locked_evidence_excerpts(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "marketing-context.json").write_text(
        json.dumps({
            "evidence_pack": [{
                "id": "evidence-1",
                "excerpt": "模型差距缩小，但工程差距正在拉开。",
            }]
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    execution = {
        "execution": {"evidence_refs": ["evidence-1"]},
    }
    delivery = {
        "scenes": [{
            "claim_evidence_quotes": {
                "evidence-1": "模型差距缩小，但工程差距正在拉开"
            }
        }]
    }

    VideoKanbanExecutionRepository._validate_claim_evidence_quotes(
        execution, workspace, delivery
    )
    delivery["scenes"][0]["claim_evidence_quotes"]["evidence-1"] = (
        "很多企业都认为工程更重要"
    )
    with pytest.raises(ValueError, match="not an exact excerpt"):
        VideoKanbanExecutionRepository._validate_claim_evidence_quotes(
            execution, workspace, delivery
        )


def test_finalizer_tool_is_only_available_inside_the_dispatched_reviewer(monkeypatch):
    from tools.marketing_tools import _official_video_finalizer_available

    for key in (
        "HERMES_PROFILE",
        "HERMES_KANBAN_TASK",
        "HERMES_TENANT",
        "HERMES_KANBAN_WORKSPACE",
    ):
        monkeypatch.delenv(key, raising=False)
    assert _official_video_finalizer_available() is False

    monkeypatch.setenv("HERMES_PROFILE", "marketing-video-reviewer")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "task-review")
    monkeypatch.setenv("HERMES_TENANT", "marketing-video-test")
    monkeypatch.setenv("HERMES_KANBAN_WORKSPACE", "/tmp/marketing-video-test")
    assert _official_video_finalizer_available() is True


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg and ffprobe are required",
)
def test_official_reviewer_finalizes_a_real_mp4_to_draft_box_idempotently(tmp_path):
    paths = _paths(tmp_path)
    entity_id, account_id = _scope(paths)
    evidence = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id=account_id,
        result={
            "results": [
                {
                    "url": "https://example.com/ai-bubble",
                    "title": "AI bubble evidence",
                    "content": "Verified evidence for an AI bubble short-video test.",
                }
            ]
        },
        session_id="official-video-integration",
    )[0]
    content = ContentAssetRepository(paths)
    plan = content.save_production_plan(
        user_id="default",
        account_id=account_id,
        plan={
            "status": "planned",
            "kind": "faceless_video",
            "objective": "把 AI 泡沫选题制作成有证据的短视频",
            "target_platforms": ["douyin"],
            "constraints": {},
            "audience_model": {"target_audience": "AI 创业者"},
        },
    )
    preflight = OperatingLoopRepository(paths).create_preflight(
        user_id="default",
        account_id=account_id,
        plan_id=plan["plan_id"],
        platform="douyin",
        session_id="official-video-integration",
        formula_version="integration-v1",
        input={"topic": "当前的 AI 是泡沫吗？"},
        scores={"overall": 0.88},
        decision={"preflight_decision": {"go": True}},
    )

    def runner(command, *, cwd):
        if command[0] == sys.executable:
            return subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
            )
        workspace = Path(command[1]).parent
        (workspace / ".kanban-root.json").write_text(
            json.dumps({"id": "task-official-root"}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    repository = VideoKanbanExecutionRepository(paths)
    execution = repository.submit(
        user_id="default",
        entity_id=entity_id,
        account_id=account_id,
        candidate_id="candidate-integration",
        plan_id=plan["plan_id"],
        preflight_id=preflight["id"],
        platform="douyin",
        topic="当前的 AI 是泡沫吗？",
        context={
            "evidence_refs": [evidence["id"]],
            "evidence_pack": [{
                "id": evidence["id"],
                "excerpt": "Verified evidence for an AI bubble short-video test.",
            }],
            "target_duration": 15,
            "aspect_ratio": "9:16",
            "minimum_shots": 4,
        },
        command_runner=runner,
        model_probe=lambda: {
            "provider": "volcengine_ark",
            "model": "doubao-seed-2-1-pro-260628",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_mode": "codex_responses",
            "probe": "function_call_ok",
        },
    )
    workspace = Path(execution["workspace_path"])
    treatment_receipt = _approve_director_treatment(
        repository,
        execution,
        evidence_id=evidence["id"],
        evidence_quote="Verified evidence for an AI bubble short-video test.",
    )
    reviewer_state = paths.user_data / "profiles/marketing-video-reviewer/state.db"
    reviewer_state.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(reviewer_state) as profile_db:
        profile_db.execute(
            """CREATE TABLE sessions (
            id TEXT PRIMARY KEY, model TEXT, cwd TEXT, input_tokens INTEGER,
            output_tokens INTEGER, cache_read_tokens INTEGER,
            cache_write_tokens INTEGER, reasoning_tokens INTEGER,
            api_call_count INTEGER, started_at REAL, ended_at REAL
            )"""
        )
        profile_db.execute(
            """INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "official-reviewer-session",
                "doubao-seed-2-1-pro-260628",
                str(workspace.resolve()),
                200,
                50,
                100,
                0,
                0,
                2,
                1.0,
                None,
            ),
        )
    output = workspace / "output"
    output.mkdir()
    final_video = output / "final.mp4"
    rendered = subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=#17232b:s=1080x1920:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(final_video),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert rendered.returncode == 0, rendered.stderr
    technical = repository._probe_final_video(final_video)
    duration = technical["duration_seconds"]
    scenes = []
    for index in range(4):
        start = round(duration * index / 4, 3)
        end = round(duration * (index + 1) / 4, 3)
        scenes.append(
            {
                "id": f"scene-{index + 1}",
                "asset_id": ("a", "b", "a", "c")[index],
                "narration_segment": {"text": f"旁白 {index + 1}"},
                "claim_evidence_refs": [evidence["id"]],
                "claim_evidence_quotes": {
                    evidence["id"]: "Verified evidence for an AI bubble short-video test."
                },
                "start_seconds": start,
                "end_seconds": end,
                "source_in": 0.0,
                "source_out": max(0.1, end - start),
                "composition_strategy": "inset_card",
                "review": {"passed": True},
            }
        )
    delivery = {
        "execution_id": execution["id"],
        "title": "AI 泡沫短视频",
        "topic": "当前的 AI 是泡沫吗？",
        "hook": "先区分估值泡沫和技术价值",
        "evidence_refs": [evidence["id"]],
        "paid_material_generation_calls": [],
        "scenes": scenes,
        "voiceover_script": "旁白 1。旁白 2。旁白 3。旁白 4。",
        "narration": {
            "actual_duration_seconds": duration,
            "receipts": [
                {
                    "provider": "volcengine",
                    "provider_task_id": "tts-integration",
                    "characters": 20,
                    "estimated_cost_cny": 0.01,
                }
            ],
        },
        "model_receipts": [
            {
                "provider": "volcengine_ark",
                "model": "doubao-seed-2-1-pro-260628",
                "usage": {"input_tokens": 20, "output_tokens": 10},
                "estimated_cost_cny": 0.01,
            }
        ],
        "tool_receipts": [{"tool": "video-use", "status": "ok"}],
    }
    material_manifest = {
        "receipts": [{"provider": "wikimedia", "status": "frozen", "cost_cny": 0}],
        "shots": [
            {
                "shot_id": scene["id"],
                "asset_id": scene["asset_id"],
                "inspection_id": f"inspection-{index}",
                "semantic_relevance": 0.8,
                "semantic_evidence": f"evidence for {scene['id']}",
            }
            for index, scene in enumerate(scenes, 1)
        ],
    }
    with repository._transaction() as db:
        for index, scene in enumerate(scenes, 1):
            db.execute(
                """INSERT INTO marketing_video_material_inspections
                (id,execution_id,shot_id,candidate_id,model,semantic_contract_hash,
                 passed,score,evidence_json,receipt_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"inspection-{index}",
                    execution["id"],
                    scene["id"],
                    f"candidate-{index}",
                        "hermes_material_scout",
                    f"contract-{index}",
                    1,
                    0.8,
                    json.dumps({
                        "semantic_evidence": f"evidence for {scene['id']}"
                    }),
                    json.dumps({
                            "provider": "local_watch",
                            "watch_no_whisper": True,
                            "cost_cny": 0,
                            "paid_services": [],
                    }),
                    "2026-07-20T00:00:00+00:00",
                ),
            )
        renderer_state = paths.user_data / "profiles/marketing-video-renderer/state.db"
        renderer_state.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(renderer_state) as profile_db:
            profile_db.execute(
                """CREATE TABLE sessions (
                id TEXT PRIMARY KEY, model TEXT, cwd TEXT, input_tokens INTEGER,
                output_tokens INTEGER, cache_read_tokens INTEGER,
                cache_write_tokens INTEGER, reasoning_tokens INTEGER,
                api_call_count INTEGER, started_at REAL, ended_at REAL
                )"""
            )
            profile_db.execute(
                """INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "official-renderer-session",
                    "doubao-seed-2-0-lite-260428",
                    str(workspace.resolve()),
                    200,
                    50,
                    100,
                    0,
                    0,
                    2,
                    1.0,
                    None,
                ),
            )
    rights_map = {
        "assets": [
            {
                "asset_id": asset_id,
                "allowed_for_use": True,
                "license": "CC0",
                "source_url": f"https://example.com/material/{asset_id}",
            }
            for asset_id in ("a", "b", "c")
        ]
    }
    review = {
        "passed": True,
        "semantic_review_pass": True,
        "caption_safe_area_pass": True,
        "audio_sync_pass": True,
        "composition_pass": True,
        "rights_pass": True,
        "repair_rounds": 1,
        "observed_video_sha256": technical["sha256"],
        "cut_observations": {
            "playable": True,
            "hook_first_three_seconds_visible": True,
            "treatment_parity": True,
            "caption_readability": True,
            "material_relevance": True,
            "evidence_alignment": True,
            "audio_present": True,
            "audio_sync": True,
            "ending_cta_present": True,
            "scores": {
                "audience_fit": 0.8,
                "platform_fit": 0.85,
                "account_fit": 0.7,
                "emotional_pull": 0.7,
                "pacing": 0.8,
                "information_density": 0.75,
                "evidence_alignment": 0.9,
            },
            "issues": [],
        },
    }
    for name, payload in (
        ("delivery.json", delivery),
        ("material-manifest.json", material_manifest),
        ("rights-map.json", rights_map),
        ("review.json", review),
    ):
        (workspace / name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    cut_receipt = repository.preflight_cut(
        execution_id=execution["id"],
        final_video_path="output/final.mp4",
        actor_profile="marketing-video-reviewer",
        tenant=execution["tenant"],
        kanban_task_id="task-reviewer",
    )
    assert cut_receipt["preflight_decision"]["go"] is True

    finalized = repository.finalize(
        execution_id=execution["id"],
        final_video_path="output/final.mp4",
        actor_profile="marketing-video-reviewer",
        tenant=execution["tenant"],
        kanban_task_id="task-reviewer",
    )
    repeated = repository.finalize(
        execution_id=execution["id"],
        final_video_path="output/final.mp4",
        actor_profile="marketing-video-reviewer",
        tenant=execution["tenant"],
        kanban_task_id="task-reviewer",
    )

    assert finalized["draft_status"] == "review_ready"
    assert finalized["production_id"] == repeated["production_id"]
    assert finalized["output_asset_id"] == repeated["output_asset_id"]
    assert repository.get(execution["id"])["status"] == "completed"
    final_draft = content.get(
        asset_id=finalized["output_asset_id"],
        user_id="default",
        account_id=account_id,
    )
    final_content = final_draft["content"]
    assert final_content["director_contract"]["measurement_plan"][
        "primary_metric"
    ] == "completion_rate"
    assert final_content["production"]["video_ir"]["preflight_lineage"] == {
        "source": preflight["id"],
        "treatment": treatment_receipt["preflight_id"],
        "cut": cut_receipt["preflight_id"],
    }
    loop = OperatingLoopRepository(paths)
    assert loop.get_preflight(treatment_receipt["preflight_id"])["status"] == (
        "used_for_action"
    )
    assert loop.get_preflight(cut_receipt["preflight_id"])["status"] == (
        "used_for_action"
    )
    canonical_delivery = json.loads(
        (workspace / "delivery.json").read_text(encoding="utf-8")
    )
    assert any(
        item.get("session_id") == "official-reviewer-session"
        for item in canonical_delivery["model_receipts"]
    )
    assert all(
        item.get("estimated_cost_cny", -1) >= 0
        for item in canonical_delivery["model_receipts"]
    )
