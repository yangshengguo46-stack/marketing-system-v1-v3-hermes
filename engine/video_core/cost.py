"""表驱动成本估算 —— ADR v2 倒置 C / 台账 VIDEO-10。

制片人 Agent 与审批 hook 共用本模块。价格表版本化：
⚠️ PRICE_TABLE_V1 为占位估计值，VIDEO-03 真实 Key 校准时必须同步核对
火山方舟真实定价并 bump 版本，记录进台账。

已写实（纯逻辑，有测试）；价格数字待校准。
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.video_core.adapter import ModelTier

PRICE_TABLE_VERSION = 1

# 占位价格（CNY）。key: (item, tier)
PRICE_TABLE_V1: dict[tuple[str, str], float] = {
    # Seedream 文生图，按张
    ("image", "final"): 0.20,
    # Seedance 视频，按 5s 段折算
    ("video_5s", ModelTier.AUDITION.value): 0.50,   # fast/lite 档，待校准
    ("video_5s", ModelTier.FINAL.value): 3.50,      # 2.0 档，待校准
    # TTS 按千字
    ("tts_1k_chars", "final"): 0.10,
}


@dataclass
class CostEstimate:
    amount: float
    currency: str
    breakdown: list[tuple[str, float]]   # (说明, 金额)
    price_table_version: int = PRICE_TABLE_VERSION

    def describe(self) -> str:
        """人类可读报价（审批展示 / 制片人报价用）。"""
        lines = [f"- {label}: ¥{amt:.2f}" for label, amt in self.breakdown]
        lines.append(f"合计: ¥{self.amount:.2f} (价格表 v{self.price_table_version})")
        return "\n".join(lines)


def estimate_images(count: int) -> CostEstimate:
    unit = PRICE_TABLE_V1[("image", "final")]
    amount = unit * count
    return CostEstimate(amount, "CNY", [(f"Seedream 图片 ×{count}", amount)])


def estimate_video(duration_sec: float, tier: ModelTier, count: int = 1) -> CostEstimate:
    segments = max(1.0, duration_sec / 5.0)
    unit = PRICE_TABLE_V1[("video_5s", tier.value)]
    amount = unit * segments * count
    label = f"Seedance {tier.value} {duration_sec:.0f}s ×{count}"
    return CostEstimate(amount, "CNY", [(label, amount)])


def estimate_production_phase(
    shot_durations_sec: list[float],
    *,
    audition_ratio: float = 1.0,   # 走替身试拍的镜头比例（关键镜头可跳过）
    audition_takes: int = 2,       # 每镜头替身试拍条数
) -> CostEstimate:
    """Phase 2 整体预估：替身试拍 + 正片。制片人做预算案的输入。"""
    breakdown: list[tuple[str, float]] = []
    total = 0.0
    audition_count = round(len(shot_durations_sec) * audition_ratio)
    if audition_count:
        aud_secs = shot_durations_sec[:audition_count]
        aud = sum(
            estimate_video(d, ModelTier.AUDITION, count=audition_takes).amount
            for d in aud_secs
        )
        breakdown.append((f"替身试拍 {audition_count} 镜头 ×{audition_takes} 条", aud))
        total += aud
    final = sum(estimate_video(d, ModelTier.FINAL).amount for d in shot_durations_sec)
    breakdown.append((f"正片 {len(shot_durations_sec)} 镜头", final))
    total += final
    return CostEstimate(total, "CNY", breakdown)


def default_budget_lines(total: float) -> list[tuple[str, float]]:
    """制片人 70/20/10 预算分配（ADR v2 倒置 C）。"""
    return [
        ("shots", round(total * 0.70, 2)),
        ("retry_reserve", round(total * 0.20, 2)),
        ("flex", round(total * 0.10, 2)),
    ]
