"""Preflight every candidate before a daily topic recommendation may leave Cron."""

from __future__ import annotations

from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_context import AccountContextRepository
from agent.marketing.domains.account_strategy import AccountStrategyRepository
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.content_policy import ContentProductionPolicy
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.domains.operating_entities import OperatingEntityRepository
from agent.marketing.domains.topic_recommendations import TopicRecommendationRepository
from agent.marketing.platform_catalog import normalize_platform_id, normalize_platforms

from .production_preflight import create_content_production_preflight
from .store import OperatingLoopRepository


DAILY_TOPIC_CONTRACT = "marketing.daily_topic_recommendations.v1"


def build_daily_topic_recommendation_batch(
    *,
    user_id: str,
    entity_id: str,
    account_id: str,
    session_id: str,
    as_of_date: str,
    candidates: list[dict[str, Any]],
    target_platforms: list[str],
    paths: MarketingDataPaths | None = None,
) -> dict[str, Any]:
    """Persist one entity/day batch; only deterministic preflight ``go`` items ship."""

    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 10:
        raise ValueError("daily topic preflight requires 1 to 10 candidates")
    platforms = normalize_platforms(target_platforms)
    if not platforms:
        raise ValueError("daily topic preflight requires at least one target platform")

    batch_store = TopicRecommendationRepository(paths)
    batch = batch_store.start_batch(
        user_id=user_id,
        entity_id=entity_id,
        account_id=account_id,
        as_of_date=as_of_date,
        source_session_id=session_id,
        target_platforms=platforms,
        input_summary={
            "contract": DAILY_TOPIC_CONTRACT,
            "candidate_count": len(candidates),
        },
    )
    if batch["status"] == "completed":
        return batch

    try:
        result_candidates = _preflight_candidates(
            user_id=user_id,
            entity_id=entity_id,
            account_id=account_id,
            session_id=session_id,
            candidates=candidates,
            target_platforms=platforms,
            paths=paths,
        )
        delivery = _canonical_delivery(
            as_of_date=as_of_date,
            batch_id=batch["id"],
            candidates=result_candidates,
        )
        return batch_store.complete_batch(
            batch_id=batch["id"],
            candidates=result_candidates,
            delivery_text=delivery,
        )
    except Exception as exc:
        batch_store.fail_batch(batch["id"], f"{type(exc).__name__}: {exc}")
        raise


def _preflight_candidates(
    *,
    user_id: str,
    entity_id: str,
    account_id: str,
    session_id: str,
    candidates: list[dict[str, Any]],
    target_platforms: list[str],
    paths: MarketingDataPaths | None,
) -> list[dict[str, Any]]:
    entity = OperatingEntityRepository(paths).get(entity_id=entity_id, user_id=user_id)
    if account_id not in entity.get("account_ids", []):
        raise ValueError("daily topic action account is outside the operating entity")

    context_store = (
        AccountContextRepository(paths) if paths else AccountContextRepository()
    )
    action_context = context_store.read(user_id=user_id, account_id=account_id)
    entity_context = context_store.read_operating_entity(
        user_id=user_id,
        entity_id=entity_id,
        focus_account_id=account_id,
    )
    shared_context = entity_context.get("shared_operating_context") or action_context
    planning_context = {
        **shared_context,
        "account_id": account_id,
        "connected": action_context.get("connected", False),
        "account": action_context.get("account"),
        "entity_id": entity_id,
    }
    audience_default = _audience_summary(planning_context)
    asset_store = ContentAssetRepository(paths)
    loop_store = OperatingLoopRepository(paths)
    knowledge_store = KnowledgeBaseRepository(paths)
    calibration = AccountStrategyRepository(paths).get_active_influence_calibration(
        user_id=user_id,
        account_id=account_id,
    )

    results: list[dict[str, Any]] = []
    for rank, raw in enumerate(candidates, start=1):
        candidate = _candidate(raw, rank=rank)
        evidence = _verified_entity_evidence(
            paths=paths,
            user_id=user_id,
            account_ids=entity.get("account_ids", []),
            evidence_ids=candidate["evidence_refs"],
        )
        objective = candidate["topic"]
        if candidate["angle"]:
            objective += f"；核心角度：{candidate['angle']}"
        candidate_platforms = normalize_platforms([
            *target_platforms,
            *candidate["platforms"],
            *candidate["platform_fit_hypotheses"],
        ])
        platform_targets = _platform_production_targets(
            entity_context=entity_context,
            platforms=candidate_platforms,
            fallback_account_id=account_id,
        )
        plan = ContentProductionPolicy().plan(
            objective=objective,
            kind="cross_platform_campaign",
            platforms=candidate_platforms,
            audience=candidate["audience"] or audience_default,
            evidence_refs=[item["id"] for item in evidence],
            constraints={
                "source": DAILY_TOPIC_CONTRACT,
                "why_now": candidate["why_now"],
                "signal_refs": candidate["signal_refs"],
                "platform_fit_hypotheses": candidate["platform_fit_hypotheses"],
            },
            account_context=planning_context,
        )
        saved_plan = asset_store.save_production_plan(
            user_id=user_id,
            account_id=account_id,
            plan=plan,
        )
        knowledge = knowledge_store.retrieve_for_preflight(
            user_id=user_id,
            account_id=account_id,
            platforms=saved_plan.get("target_platforms") or [],
            content_kind=saved_plan["kind"],
        )
        preflight = create_content_production_preflight(
            loop_store,
            {
                "user_id": user_id,
                "account_id": account_id,
                "session_id": session_id,
                "plan_id": saved_plan["plan_id"],
                "plan": saved_plan,
                "evidence_refs": [item["id"] for item in evidence],
                "knowledge_context": knowledge,
                "influence_weights": calibration.get("weights")
                if calibration
                else None,
                "influence_calibration_id": calibration.get("id")
                if calibration
                else None,
            },
        )
        decision = preflight["preflight_decision"]
        platform_matches = _platform_match_scores(
            platforms=saved_plan["target_platforms"],
            hypotheses=candidate["platform_fit_hypotheses"],
            preflight=preflight,
        )
        strong_platforms = [
            item["platform"] for item in platform_matches if item["strong_match"]
        ]
        recommendation_type = (
            "general" if len(strong_platforms) >= 2 else "platform_specific"
        )
        recommended_platforms = (
            strong_platforms
            if recommendation_type == "general"
            else [platform_matches[0]["platform"]]
        )
        results.append({
            **candidate,
            "rank": rank,
            "plan_id": saved_plan["plan_id"],
            "preflight_id": preflight["preflight_id"],
            "target_platforms": saved_plan["target_platforms"],
            "evidence_refs": [item["id"] for item in evidence],
            "decision_status": decision["status"],
            "recommendation_eligible": decision.get("go") is True,
            "influence_score": float(
                (preflight.get("influence_score") or {}).get("score") or 0
            ),
            "recommendation_type": recommendation_type,
            "recommended_platforms": recommended_platforms,
            "platform_targets": {
                platform: platform_targets[platform]
                for platform in recommended_platforms
                if platform in platform_targets
            },
            "platform_matches": platform_matches,
            "preflight": {
                "status": decision["status"],
                "score": decision.get("score"),
                "primary_reason": decision.get("primary_reason"),
                "blockers": decision.get("blockers") or [],
                "warnings": decision.get("warnings") or [],
                "next_action": decision.get("next_action"),
            },
            "platform_blueprints": saved_plan.get("platform_blueprints") or {},
        })
    return results


def _platform_production_targets(
    *,
    entity_context: dict[str, Any],
    platforms: list[str],
    fallback_account_id: str,
) -> dict[str, dict[str, Any]]:
    """Bind a recommended platform to its real entity account when one exists.

    The daily topic batch is entity-scoped, while older production tables still
    require an execution account.  We therefore keep the fallback account only
    as a compatibility execution owner and explicitly record that it is *not* a
    platform-specific personalization source.  A missing target account lowers
    confidence; it never prevents public-prior drafting.
    """

    contexts = [
        item
        for item in (entity_context.get("linked_account_contexts") or [])
        if isinstance(item, dict)
    ]
    by_platform: dict[str, list[dict[str, Any]]] = {}
    for context in contexts:
        account = context.get("account") if isinstance(context.get("account"), dict) else {}
        platform = str(account.get("platform") or "").strip()
        account_id = str(context.get("account_id") or account.get("id") or "").strip()
        if platform and account_id and context.get("connected") is True:
            by_platform.setdefault(platform, []).append(context)

    targets: dict[str, dict[str, Any]] = {}
    for platform in platforms:
        matches = by_platform.get(platform) or []
        target = matches[0] if len(matches) == 1 else None
        target_account_id = str((target or {}).get("account_id") or "").strip()
        targets[platform] = {
            "platform": platform,
            "account_id": target_account_id or None,
            # Legacy repositories still require an account-scoped storage
            # owner. Keep the action/anchor account for compatibility while
            # recording the real platform account separately for modelling
            # and later publish effects. Entity ownership remains canonical.
            "execution_account_id": fallback_account_id,
            "binding_status": (
                "linked_platform_account"
                if target_account_id
                else (
                    "ambiguous_platform_accounts"
                    if len(matches) > 1
                    else "public_prior_only_no_linked_account"
                )
            ),
            "personalization_available": bool(target_account_id),
            "candidate_account_ids": [
                str(item.get("account_id") or "") for item in matches
            ],
        }
    return targets


def _candidate(value: Any, *, rank: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"candidate {rank} must be an object")
    topic = _bounded(value.get("topic"), field=f"candidate {rank} topic", limit=300)
    evidence_refs = _refs(value.get("evidence_refs"), limit=30)
    return {
        "topic": topic,
        "angle": _optional(value.get("angle"), limit=800),
        "why_now": _optional(value.get("why_now"), limit=800),
        "audience": _optional(value.get("audience"), limit=500),
        "platforms": normalize_platforms(value.get("platforms") or []),
        "evidence_refs": evidence_refs,
        "signal_refs": _refs(value.get("signal_refs"), limit=50),
        "platform_fit_hypotheses": _platform_fit_hypotheses(
            value.get("platform_fit_hypotheses"),
            evidence_refs=evidence_refs,
        ),
    }


def _platform_fit_hypotheses(
    value: Any, *, evidence_refs: list[str]
) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise ValueError("platform_fit_hypotheses must be a list")
    if len(value) > 30:
        raise ValueError("platform_fit_hypotheses exceeds 30 entries")
    allowed_evidence = set(evidence_refs)
    result: dict[str, dict[str, Any]] = {}
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("each platform fit hypothesis must be an object")
        platform = normalize_platform_id(raw.get("platform"))
        if platform in result:
            raise ValueError(f"duplicate platform fit hypothesis: {platform}")
        score = raw.get("match_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("platform fit match_score must be numeric")
        score_value = float(score)
        if not 0 <= score_value <= 100:
            raise ValueError("platform fit match_score must be between 0 and 100")
        rationale = _bounded(
            raw.get("rationale"),
            field=f"platform fit rationale for {platform}",
            limit=600,
        )
        refs = _refs(raw.get("evidence_refs"), limit=20)
        if any(ref not in allowed_evidence for ref in refs):
            raise ValueError(
                "platform fit hypothesis evidence must belong to the candidate evidence pack"
            )
        result[platform] = {
            "match_score": round(score_value, 1),
            "rationale": rationale,
            "evidence_refs": refs,
        }
    return result


def _platform_match_scores(
    *,
    platforms: list[str],
    hypotheses: dict[str, dict[str, Any]],
    preflight: dict[str, Any],
) -> list[dict[str, Any]]:
    """Recalibrate model hypotheses with the immutable preflight receipt."""

    influence_score = float((preflight.get("influence_score") or {}).get("score") or 0)
    assessments = preflight.get("platform_assessments") or {}
    matches: list[dict[str, Any]] = []
    for platform in platforms:
        assessment = (
            assessments.get(platform)
            if isinstance(assessments.get(platform), dict)
            else {}
        )
        profile_fit = max(0.0, min(100.0, float(assessment.get("fit") or 0) * 100))
        hypothesis = hypotheses.get(platform)
        if hypothesis:
            score = round(
                float(hypothesis["match_score"]) * 0.65
                + influence_score * 0.25
                + profile_fit * 0.10
            )
            rationale = str(hypothesis["rationale"])
            evidence_refs = list(hypothesis.get("evidence_refs") or [])
            basis = "candidate_hypothesis_recalibrated_by_preflight"
        else:
            score = round(influence_score * 0.7 + profile_fit * 0.3)
            rationale = "未提供平台专项假设，使用全局预演与平台知识覆盖度保守估计。"
            evidence_refs = []
            basis = "preflight_fallback"
        guidance_status = str(assessment.get("guidance_status") or "")
        if guidance_status.startswith("generic_"):
            score = min(score, 64)
        matches.append({
            "platform": platform,
            "match_score": max(0, min(100, score)),
            "strong_match": score >= 75,
            "rationale": rationale,
            "evidence_refs": evidence_refs,
            "basis": basis,
            "guidance_status": guidance_status,
        })
    return sorted(
        matches,
        key=lambda item: (-int(item["match_score"]), platforms.index(item["platform"])),
    )


def _verified_entity_evidence(
    *,
    paths: MarketingDataPaths | None,
    user_id: str,
    account_ids: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    return EvidenceRepository(paths).require_verified_across_accounts(
        user_id=user_id,
        account_ids=account_ids,
        evidence_ids=evidence_ids,
        require_any=False,
    )


def _audience_summary(context: dict[str, Any]) -> str:
    lifecycle = context.get("lifecycle") or {}
    audience = lifecycle.get("audience_hypothesis") or {}
    segments = audience.get("segments") if isinstance(audience, dict) else []
    if isinstance(segments, list):
        values = [
            str(item.get("name") if isinstance(item, dict) else item).strip()
            for item in segments
        ]
        values = [item for item in values if item]
        if values:
            return "、".join(values)[:500]
    return ""


def _canonical_delivery(
    *, as_of_date: str, batch_id: str, candidates: list[dict[str, Any]]
) -> str:
    recommended = [item for item in candidates if item["recommendation_eligible"]]
    if not recommended:
        return "[SILENT]"
    lines = [f"## {as_of_date} 今日选题（已逐条预演）", ""]
    index = 0
    groups = (
        (
            "通用选题",
            [item for item in recommended if _recommendation_type(item) == "general"],
        ),
        (
            "平台推荐选题",
            [
                item
                for item in recommended
                if _recommendation_type(item) == "platform_specific"
            ],
        ),
    )
    for label, items in groups:
        if not items:
            continue
        lines.extend([f"### {label}", ""])
        for item in items:
            index += 1
            match_text = "；".join(
                f"{match['platform']} {int(match['match_score'])}%"
                for match in item.get("platform_matches") or []
            )
            lines.extend([
                f"#### {index}. {item['topic']}",
                f"- 角度：{item['angle'] or '围绕选题本身形成可验证判断'}",
                f"- 为什么是现在：{item['why_now'] or '以绑定证据与当日信号为准'}",
                f"- 平台预演匹配：{match_text or '等待平台专项校准'}",
                f"- 预演：通过，InfluenceScore {item['influence_score']:.1f}；{item['preflight']['primary_reason']}",
                f"- 回执：`{item['plan_id']}` / `{item['preflight_id']}`",
                "- 各平台制作：",
            ])
            for platform, blueprint in item["platform_blueprints"].items():
                lines.append(
                    f"  - **{platform}**：{', '.join(blueprint['recommended_formats'])}；"
                    f"开头：{blueprint['opening_contract']}；结构：{blueprint['structure_contract']}；"
                    f"视觉：{blueprint['visual_contract']}；CTA：{blueprint['cta_contract']}"
                )
            if item["preflight"]["warnings"]:
                lines.append("- 观察项：" + "；".join(item["preflight"]["warnings"]))
            lines.append("")
    research_count = len(candidates) - len(recommended)
    lines.extend([
        f"> 批次 `{batch_id}`；推荐 {len(recommended)} 条；另有 {research_count} 条未通过预演，已留在研究池，不向你推荐。",
    ])
    return "\n".join(lines).strip()


def _recommendation_type(item: dict[str, Any]) -> str:
    value = str(item.get("recommendation_type") or "")
    if value in {"general", "platform_specific"}:
        return value
    return (
        "general"
        if len(item.get("target_platforms") or []) >= 2
        else "platform_specific"
    )


def _bounded(value: Any, *, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _optional(value: Any, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _refs(value: Any, *, limit: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("candidate references must be a list")
    result = list(
        dict.fromkeys(
            str(item or "").strip() for item in value if str(item or "").strip()
        )
    )
    if len(result) > limit:
        raise ValueError(f"candidate references exceed {limit} entries")
    return result
