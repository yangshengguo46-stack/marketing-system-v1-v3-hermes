import json
import hashlib
import sqlite3

import hermes_state
import model_tools
import pytest
from hermes_state import SessionDB
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    ArticleDraftValidator,
    ContentAssetRepository,
    ContentProductionPolicy,
    EvidenceRepository,
)
from agent.marketing.evidence_capture import enrich_tool_result_with_evidence
from model_tools import get_tool_definitions, handle_function_call


def _paths(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"id": "acct-1", "platform": "douyin", "label": "主账号", "status": "active"},
                    {"id": "acct-2", "platform": "xiaohongshu", "label": "副账号", "status": "active"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=config_dir,
        agent_db=tmp_path / "agent-runtime" / "agent_core.db",
    )


def _bind_session(tmp_path, monkeypatch, account_id="acct-1"):
    paths = _paths(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    db.create_session(
        "session-1",
        "tui",
        marketing_user_id="default",
        marketing_account_id=account_id,
    )
    db.close()
    return paths


def _capture_evidence(*, session_id="session-1", task_id="session-1"):
    raw_content = "该报告记录了 AI 辅助工作流程的原始样本、方法与研究边界。"
    summary = "该报告记录了 AI 辅助工作流程的样本和研究边界。"
    enriched = enrich_tool_result_with_evidence(
        tool_name="web_extract",
        args={"urls": ["https://Example.com/report?utm_source=test#section"]},
        result=json.dumps(
            {
                "results": [
                    {
                        "url": "https://Example.com/report?utm_source=test#section",
                        "title": "AI 工作方式报告",
                        "content": summary,
                        "content_origin": "llm_summary",
                        "source_content_sha256": hashlib.sha256(
                            raw_content.encode("utf-8")
                        ).hexdigest(),
                        "error": None,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        task_id=task_id,
        session_id=session_id,
        tool_call_id="call-web-1",
    )
    payload = json.loads(enriched)
    return payload, payload["marketing_evidence"]["records"][0]["evidence_id"]


def _long_article(evidence_id, voice):
    sections = []
    for heading, idea in (
        ("先说结论", "先把判断边界说清楚，再讨论工具能解决什么问题"),
        ("证据意味着什么", "来源只能支持有限结论，不能把相关性包装成确定因果"),
        ("真正的使用方法", "从一个重复任务开始，记录输入、人工判断与输出差异"),
        ("容易踩的坑", "效率提升不等于岗位价值提升，保留复核和责任边界"),
        ("下一步行动", "用一周小实验验证时间成本、错误率和实际收益"),
    ):
        paragraph = (f"{voice}：{idea}。这段内容围绕真实工作场景展开，并说明适用条件和反例。" * 8)
        sections.append(f"## {heading}\n\n{paragraph} [{evidence_id}]")
    return "\n\n".join(sections)


@pytest.mark.parametrize(
    ("objective", "kind"),
    [
        ("写一篇公众号软文", "article_soft"),
        ("做一条授权素材拼接的不露脸视频", "faceless_video"),
        ("做一条真人数字人高质量视频", "premium_human_video"),
    ],
)
def test_native_planner_selects_three_connected_lanes(objective, kind):
    result = ContentProductionPolicy().plan(objective=objective)

    assert result["kind"] == kind
    assert result["architecture"] == "hermes-native-shared-capability-pool"
    assert "account_context" in result["capabilities"]
    assert "evidence_research" in result["capabilities"]
    assert "copywriting" in result["capabilities"]
    if kind != "article_soft":
        assert "editing_render" in result["capabilities"]


def test_native_content_tools_plan_save_and_resume_in_bound_account(tmp_path, monkeypatch):
    paths = _bind_session(tmp_path, monkeypatch)
    extract_result, evidence_id = _capture_evidence()
    plan_args = {
        "objective": "写一篇面向 AI 入门职场人的公众号软文",
        "platforms": ["wechat_official"],
        "audience": "想提高效率的职场人",
        "evidence_refs": [evidence_id],
    }
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            plan_args,
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    created = json.loads(
        handle_function_call(
            "marketing_draft_article_create",
            {
                "title": "普通人如何把 AI 变成工作搭档",
                "plan_id": planned["plan_id"],
                "topic": "AI 工作流",
                "hook": "不是多学一个工具，而是重做工作方式",
                "parent_body_markdown": _long_article(evidence_id, "父稿"),
                "platform_variants": {
                    "wechat_official": {
                        "title": "普通人如何把 AI 变成工作搭档",
                        "summary": "从一个真实任务开始改造工作流",
                        "body_markdown": _long_article(evidence_id, "公众号版本更重场景和行动"),
                        "tags": ["AI", "工作流"],
                        "cta": "从你最重复的一项任务开始记录。",
                    }
                },
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    listed = json.loads(
        handle_function_call(
            "marketing_read_content_assets",
            {"status": "review_ready"},
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    replanned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            plan_args,
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert planned["account_scope"]["account_id"] == "acct-1"
    assert planned["checkpoint_status"] == "planned"
    assert planned["preflight"]["id"].startswith("preflight_")
    assert planned["preflight"]["formula_version"] == "content-production-preflight-v0.1"
    assert planned["preflight"]["decision"]["version"] == "preflight-decision-v0.1"
    assert planned["preflight"]["influence_score"]["version"] == "influenceos-score-v0.1"
    assert planned["recommended_next_action"].startswith("使用已固化")
    assert planned["platform_stylebooks"]["wechat_official"]["guidance_status"].startswith(
        "operational_guidance"
    )
    assert extract_result["marketing_evidence"]["records"][0]["status"] == "verified"
    assert created["account_id"] == "acct-1"
    assert created["content"]["_created_by"] == "hermes-native-marketing"
    assert created["content"]["_production_plan_id"] == planned["plan_id"]
    assert created["content"]["_provenance_evidence_refs"] == [evidence_id]
    assert created["content"]["_evidence_verification_level"] == "source_integrity"
    assert created["content"]["feature_snapshot"]["retro_contract"]["mutable"] is False
    assert created["content"]["feature_snapshot"]["evidence"]["ready"] is True
    assert created["content"]["schema"] == "marketing.article_bundle.v1"
    assert created["content"]["review_status"] == "ready_for_human_review"
    assert created["content"]["validation"]["ready"] is True
    assert created["content"]["platform_stylebooks"]["wechat_official"]["cover"]["primary_ratio"] == "2.35:1"
    assert listed["total"] == 1
    assert listed["assets"][0]["id"] == created["id"]
    assert replanned["plan_id"] == planned["plan_id"]
    assert replanned["checkpoint_status"] == "review_ready"
    assert ContentAssetRepository(paths).list(user_id="default", account_id="acct-2")["total"] == 0


def test_content_write_schema_cannot_override_account_scope():
    definitions = get_tool_definitions(enabled_toolsets=["marketing"], quiet_mode=True)
    by_name = {item["function"]["name"]: item["function"] for item in definitions}

    create_properties = by_name["marketing_draft_content_create"]["parameters"]["properties"]
    article_properties = by_name["marketing_draft_article_create"]["parameters"]["properties"]
    plan_properties = by_name["marketing_plan_content_production"]["parameters"]["properties"]

    assert "account_id" not in create_properties
    assert "account_id" not in article_properties
    assert "account_id" not in plan_properties
    assert "marketing_read_evidence_pack" in by_name
    assert "marketing_read_content_assets" in by_name


def test_content_repository_rejects_reserved_provenance_keys(tmp_path):
    paths = _paths(tmp_path)
    repository = ContentAssetRepository(paths)

    with pytest.raises(ValueError, match="reserved"):
        repository.create_draft(
            user_id="default",
            account_id="acct-1",
            title="bad",
            plan_id="production_plan_missing",
            asset_type="script",
            platform="douyin",
            production_kind="faceless_video",
            content={"_created_by": "model-forged"},
        )


def test_draft_requires_real_plan_in_same_account_scope(tmp_path):
    paths = _paths(tmp_path)
    repository = ContentAssetRepository(paths)
    evidence_id = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id="acct-1",
        result={
            "results": [
                {
                    "url": "https://example.com/report",
                    "title": "报告",
                    "content": "真实采集的正文",
                }
            ]
        },
        session_id="session-1",
    )[0]["id"]

    with pytest.raises(KeyError, match="plan not found"):
        repository.create_draft(
            user_id="default",
            account_id="acct-1",
            title="不能绕过工单",
            plan_id="production_plan_invented",
            asset_type="script",
            platform="douyin",
            production_kind="faceless_video",
            content={"markdown": "正文"},
            evidence_refs=[evidence_id],
        )


def test_raw_url_cannot_be_promoted_to_verified_evidence(tmp_path, monkeypatch):
    _bind_session(tmp_path, monkeypatch)

    result = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            {
                "objective": "写一篇有事实依据的知乎文章",
                "audience": "AI 入门用户",
                "evidence_refs": ["source:https://example.com/report"],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert "invalid EvidencePack id" in result["error"]


def test_evidence_capture_is_idempotent_and_account_scoped(tmp_path, monkeypatch):
    paths = _bind_session(tmp_path, monkeypatch)
    first_payload, evidence_id = _capture_evidence()
    second_payload, second_id = _capture_evidence()

    assert evidence_id == second_id
    assert first_payload["marketing_evidence"]["citation_rule"].startswith("Use these evidence_id")
    pack = EvidenceRepository(paths).list(user_id="default", account_id="acct-1")
    assert pack["total"] == 1
    assert pack["records"][0]["id"] == evidence_id
    assert pack["records"][0]["canonical_url"] == "https://example.com/report"
    assert len(pack["records"][0]["content_sha256"]) == 64
    assert pack["records"][0]["content_sha256"] == hashlib.sha256(
        "该报告记录了 AI 辅助工作流程的原始样本、方法与研究边界。".encode("utf-8")
    ).hexdigest()
    assert pack["records"][0]["metadata"]["excerpt_origin"] == "llm_summary"
    assert pack["records"][0]["metadata"]["source_hash_origin"] == "native_collector_raw_content"
    assert pack["records"][0]["metadata"]["claim_truth_verified"] is False
    assert EvidenceRepository(paths).list(user_id="default", account_id="acct-2")["total"] == 0


def test_failed_or_empty_web_extract_is_not_evidence(tmp_path, monkeypatch):
    paths = _bind_session(tmp_path, monkeypatch)
    unchanged = enrich_tool_result_with_evidence(
        tool_name="web_extract",
        args={"urls": ["https://example.com/missing"]},
        result=json.dumps(
            {
                "results": [
                    {
                        "url": "https://example.com/missing",
                        "content": "",
                        "error": "not found",
                    }
                ]
            }
        ),
        task_id="session-1",
        session_id="session-1",
    )

    assert "marketing_evidence" not in json.loads(unchanged)
    assert EvidenceRepository(paths).list(user_id="default", account_id="acct-1")["total"] == 0


def test_model_tools_dispatch_native_seam_returns_evidence_ids(tmp_path, monkeypatch):
    paths = _bind_session(tmp_path, monkeypatch)

    def fake_dispatch(name, args, **_kwargs):
        assert name == "web_extract"
        assert args["urls"] == ["https://example.com/native"]
        return json.dumps(
            {
                "results": [
                    {
                        "url": "https://example.com/native",
                        "title": "原生采集",
                        "content": "这是经过 Hermes web_extract 主调度器返回的内容。",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(model_tools.registry, "dispatch", fake_dispatch)
    result = json.loads(
        model_tools.handle_function_call(
            "web_extract",
            {"urls": ["https://example.com/native"]},
            task_id="session-1",
            session_id="session-1",
            tool_call_id="native-call-1",
            enabled_toolsets=["web", "marketing"],
        )
    )

    evidence_id = result["marketing_evidence"]["records"][0]["evidence_id"]
    record = EvidenceRepository(paths).require_verified(
        user_id="default",
        account_id="acct-1",
        evidence_ids=[evidence_id],
    )[0]
    assert record["tool_call_id"] == "native-call-1"
    assert record["session_id"] == "session-1"


def test_draft_rejects_evidence_from_another_account(tmp_path, monkeypatch):
    paths = _bind_session(tmp_path, monkeypatch)
    foreign_id = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id="acct-2",
        result={
            "results": [
                {
                    "url": "https://example.com/foreign",
                    "title": "副账号资料",
                    "content": "只属于副账号的证据",
                }
            ]
        },
        session_id="session-2",
    )[0]["id"]
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            {
                "objective": "写一篇公众号软文",
                "audience": "AI 入门用户",
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    result = json.loads(
        handle_function_call(
            "marketing_draft_article_create",
            {
                "title": "不能串账号",
                "plan_id": planned["plan_id"],
                "parent_body_markdown": _long_article(foreign_id, "父稿"),
                "platform_variants": {
                    "wechat_official": {
                        "title": "不能串账号",
                        "body_markdown": _long_article(foreign_id, "公众号"),
                    }
                },
                "evidence_refs": [foreign_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert "current account scope" in result["error"]


def test_generic_draft_cannot_bypass_article_validation(tmp_path, monkeypatch):
    _bind_session(tmp_path, monkeypatch)
    _, evidence_id = _capture_evidence()
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            {
                "objective": "写一篇知乎文章",
                "platforms": ["zhihu"],
                "audience": "AI 入门用户",
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    result = json.loads(
        handle_function_call(
            "marketing_draft_content_create",
            {
                "title": "绕过校验",
                "plan_id": planned["plan_id"],
                "platform": "zhihu",
                "production_kind": "article_soft",
                "content": {"markdown": "几句话冒充长文"},
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert "validated article bundle path" in result["error"]


def test_incomplete_or_duplicated_article_variants_are_saved_but_not_review_ready(
    tmp_path, monkeypatch
):
    _bind_session(tmp_path, monkeypatch)
    _, evidence_id = _capture_evidence()
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            {
                "objective": "写一篇知乎和公众号长文",
                "platforms": ["zhihu", "wechat_official"],
                "audience": "AI 入门用户",
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    parent = _long_article(evidence_id, "完全相同的版本")
    created = json.loads(
        handle_function_call(
            "marketing_draft_article_create",
            {
                "title": "同一份稿子不能复制到所有平台",
                "plan_id": planned["plan_id"],
                "parent_body_markdown": parent,
                "platform_variants": {
                    "zhihu": {"title": "知乎版", "body_markdown": parent},
                    "wechat_official": {"title": "公众号版", "body_markdown": parent},
                },
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert created["status"] == "draft"
    assert created["content"]["review_status"] == "needs_revision"
    issues = created["content"]["validation"]["issues"]
    assert "platform_variants_copy_parent" in issues
    assert "platform_variants_not_distinct" in issues
    assert created["content"]["prediction"]["traffic_range"] is None


def test_article_claim_audit_blocks_uncited_quantitative_market_claims(
    tmp_path, monkeypatch
):
    _bind_session(tmp_path, monkeypatch)
    _, evidence_id = _capture_evidence()
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            {
                "objective": "写一篇有证据的 AI 教育长文",
                "platforms": ["zhihu"],
                "audience": "家长和教师",
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    unsupported = "市场上90%以上的培训班都只教提示词，这个比例没有任何来源。"
    created = json.loads(
        handle_function_call(
            "marketing_draft_article_create",
            {
                "title": "AI 教育真正该教什么",
                "plan_id": planned["plan_id"],
                "parent_body_markdown": f"{_long_article(evidence_id, '父稿')}\n\n{unsupported}",
                "platform_variants": {
                    "zhihu": {
                        "title": "AI 教育真正该教什么",
                        "body_markdown": (
                            f"{_long_article(evidence_id, '知乎独立版本')}\n\n{unsupported}"
                        ),
                    }
                },
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert created["status"] == "draft"
    validation = created["content"]["validation"]
    assert "factual_claim_citation_missing" in validation["issues"]
    findings = validation["claim_audit"]["uncited_findings"]
    assert any(
        any(token.startswith("90%") for token in item["numeric_tokens"])
        for item in findings
    )


def test_article_claim_audit_accepts_cited_number_found_in_evidence_excerpt():
    evidence_id = "evidence_" + "a" * 28
    records = [
        {
            "id": evidence_id,
            "title": "行动计划",
            "excerpt": "行动计划提出，到2030年人工智能与教育深度融合格局基本形成。",
            "canonical_url": "https://example.com/policy",
            "captured_at": "2026-07-10T00:00:00+00:00",
            "content_sha256": "b" * 64,
            "verification_level": "source_integrity",
        }
    ]
    supported = f"教育部政策提出，到2030年相关建设目标将进一步推进。 [{evidence_id}]"
    bundle = ArticleDraftValidator().build_bundle(
        title="AI 教育行动计划",
        parent_body_markdown=f"{_long_article(evidence_id, '父稿')}\n\n{supported}",
        target_platforms=["zhihu"],
        variants={
            "zhihu": {
                "title": "AI 教育行动计划：边界与行动",
                "body_markdown": f"{_long_article(evidence_id, '知乎独立版本')}\n\n{supported}",
            }
        },
        evidence_records=records,
    )

    assert bundle["review_status"] == "ready_for_human_review"
    assert bundle["validation"]["claim_audit"]["ready"] is True


def test_existing_v1_article_is_revalidated_and_downgraded_on_repository_open(
    tmp_path, monkeypatch
):
    paths = _bind_session(tmp_path, monkeypatch)
    _, evidence_id = _capture_evidence()
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            {
                "objective": "迁移旧文章质量门",
                "platforms": ["zhihu"],
                "audience": "家长和教师",
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    unsupported = "市场上90%以上的培训班都只教提示词，这个比例没有来源。"
    created = json.loads(
        handle_function_call(
            "marketing_draft_article_create",
            {
                "title": "旧版误判文章",
                "plan_id": planned["plan_id"],
                "parent_body_markdown": f"{_long_article(evidence_id, '父稿')}\n\n{unsupported}",
                "platform_variants": {
                    "zhihu": {
                        "title": "旧版误判文章",
                        "body_markdown": (
                            f"{_long_article(evidence_id, '知乎版本')}\n\n{unsupported}"
                        ),
                    }
                },
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    old_payload = dict(created["content"])
    old_payload["review_status"] = "ready_for_human_review"
    old_payload["validation"] = {
        "version": "marketing.article_validation.v1",
        "ready": True,
        "issues": [],
    }
    with sqlite3.connect(paths.agent_db) as db:
        db.execute(
            "UPDATE content_assets SET content_json=?, status='review_ready' WHERE id=?",
            (json.dumps(old_payload, ensure_ascii=False), created["id"]),
        )
        db.execute(
            "UPDATE content_production_plans SET status='review_ready' WHERE id=?",
            (planned["plan_id"],),
        )

    repository = ContentAssetRepository(paths)
    migrated = repository.get(
        asset_id=created["id"], user_id="default", account_id="acct-1"
    )

    assert migrated["status"] == "draft"
    assert migrated["version"] == 2
    assert migrated["content"]["review_status"] == "needs_revision"
    assert migrated["content"]["validation"]["version"] == "marketing.article_validation.v2"
    assert "factual_claim_citation_missing" in migrated["content"]["validation"]["issues"]
    with sqlite3.connect(paths.agent_db) as db:
        checkpoint_status = db.execute(
            "SELECT status FROM content_production_plans WHERE id=?",
            (planned["plan_id"],),
        ).fetchone()[0]
    assert checkpoint_status == "draft_created"


def test_article_revision_creates_immutable_version_chain(tmp_path, monkeypatch):
    _bind_session(tmp_path, monkeypatch)
    _, evidence_id = _capture_evidence()
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            {
                "objective": "写一篇可持续修订的知乎文章",
                "platforms": ["zhihu"],
                "audience": "AI 入门用户",
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    first = json.loads(
        handle_function_call(
            "marketing_draft_article_create",
            {
                "title": "第一版",
                "plan_id": planned["plan_id"],
                "parent_body_markdown": _long_article(evidence_id, "父稿第一版"),
                "platform_variants": {
                    "zhihu": {
                        "title": "第一版知乎稿",
                        "body_markdown": _long_article(evidence_id, "知乎第一版"),
                    }
                },
                "evidence_refs": [evidence_id],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    second = json.loads(
        handle_function_call(
            "marketing_draft_article_create",
            {
                "title": "第二版",
                "plan_id": planned["plan_id"],
                "parent_body_markdown": _long_article(evidence_id, "父稿第二版"),
                "platform_variants": {
                    "zhihu": {
                        "title": "第二版知乎稿",
                        "body_markdown": _long_article(evidence_id, "知乎第二版"),
                    }
                },
                "evidence_refs": [evidence_id],
                "revision_of": first["id"],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert first["version"] == 1
    assert second["version"] == 2
    assert second["parent_id"] == first["id"]
    repository = ContentAssetRepository()
    parent = repository.get(
        asset_id=first["id"], user_id="default", account_id="acct-1"
    )
    assert parent["status"] == "superseded"
    active = repository.list(user_id="default", account_id="acct-1")
    assert [item["id"] for item in active["assets"]] == [second["id"]]
    history = repository.list(
        user_id="default", account_id="acct-1", status="superseded"
    )
    assert [item["id"] for item in history["assets"]] == [first["id"]]
