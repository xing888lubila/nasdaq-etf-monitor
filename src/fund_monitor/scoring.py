from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreItem:
    name: str
    score: int
    label: str
    reason: str


@dataclass(frozen=True)
class ScoreResult:
    items: tuple[ScoreItem, ...]
    total_score: int
    trend_label: str
    upside_probability: int
    downside_probability: int
    recommended_buy: int
    key_variable: str
    rationale: str


@dataclass(frozen=True)
class CashPolicy:
    total_cash: int = 1000
    cash_floor: int = 500
    max_investable: int = 500
    normal_bullish_buy: int = 30
    neutral_buy: int = 50
    bearish_buy: int = 70
    extreme_bearish_buy: int = 100
    current_cash: int = 1000


def score_nq_futures(change_pct: float | None) -> ScoreItem:
    if change_pct is None:
        return ScoreItem("NQ futures", 0, "中性", "NQ 数据暂不可用。")
    if change_pct <= -1.0:
        return ScoreItem("NQ futures", -2, "明显偏空", f"NQ 当前下跌 {change_pct:.2f}%，盘前压力已经比较明确。")
    if change_pct <= -0.5:
        return ScoreItem("NQ futures", -1, "偏空", f"NQ 当前下跌 {change_pct:.2f}%，今晚纳指低开或走弱风险较高。")
    if change_pct >= 0.3:
        return ScoreItem("NQ futures", 1, "偏多", f"NQ 当前上涨 {change_pct:.2f}%，夜盘风险偏好较强。")
    return ScoreItem("NQ futures", 0, "中性", f"NQ 当前 {change_pct:.2f}%，仍在中性区间内。")


def score_yields(two_year_bp: float | None, ten_year_bp: float | None) -> ScoreItem:
    if two_year_bp is None or ten_year_bp is None:
        return ScoreItem("美债收益率", 0, "中性", "2Y/10Y 收益率数据不完整。")
    if two_year_bp >= 10 and ten_year_bp >= 10:
        return ScoreItem("美债收益率", -2, "明显偏空", "2Y 和 10Y 同时上行至少 10bp，利率压力明显。")
    if two_year_bp >= 5 and ten_year_bp >= 5:
        return ScoreItem("美债收益率", -1, "偏空", "2Y 和 10Y 同时上行至少 5bp，对纳指估值偏不利。")
    if two_year_bp <= -10 and ten_year_bp <= -10:
        return ScoreItem("美债收益率", 1, "偏多", "2Y 和 10Y 同时下行至少 10bp，利率压力缓解，但需确认是否来自衰退恐慌。")
    if two_year_bp <= -5 and ten_year_bp <= -5:
        return ScoreItem("美债收益率", 1, "偏多", "2Y 和 10Y 同时下行至少 5bp，对纳指估值偏有利。")
    if two_year_bp > 0 and ten_year_bp < 0:
        return ScoreItem("美债收益率", -1, "偏空", "2Y 上行而 10Y 下行，偏向加息预期或倒挂压力。")
    if two_year_bp < 0 and ten_year_bp > 0:
        return ScoreItem("美债收益率", 0, "分化", "2Y 下行而 10Y 上行，需要结合新闻判断是增长改善还是通胀压力。")
    return ScoreItem("美债收益率", 0, "中性", f"2Y 变化 {two_year_bp:+.0f}bp，10Y 变化 {ten_year_bp:+.0f}bp，方向不够强。")


def score_macro_event(actual_bias: str | None, event_name: str | None = None) -> ScoreItem:
    name = event_name or "scheduled macro release"
    bias = (actual_bias or "neutral").lower()
    if bias in {"bullish", "cooling", "soft"}:
        return ScoreItem("8:30 ET 宏观数据", 1, "偏多", f"{name} 解读为对纳指偏有利。")
    if bias in {"bearish", "hot", "hawkish"}:
        return ScoreItem("8:30 ET 宏观数据", -1, "偏空", f"{name} 解读为对纳指偏不利。")
    if bias in {"strong_bearish", "very_hot"}:
        return ScoreItem("8:30 ET 宏观数据", -2, "明显偏空", f"{name} 显示较强通胀或利率压力。")
    return ScoreItem("8:30 ET 宏观数据", 0, "中性", f"{name} 暂无明确方向，等待实际公布值。")


def score_tech_relative(qqq_pct: float | None, spy_pct: float | None, dia_pct: float | None, smh_pct: float | None = None) -> ScoreItem:
    if qqq_pct is None or spy_pct is None or dia_pct is None:
        return ScoreItem("科技股相对强弱", 0, "中性", "QQQ/SPY/DIA 数据不完整。")
    if qqq_pct < 0 and spy_pct <= -1.0 and dia_pct <= -1.0:
        return ScoreItem("科技股相对强弱", 0, "全市场避险", "QQQ、SPY 和 DIA 同跌，属于全市场风险偏好下降，不是科技股单独弱。")
    if qqq_pct < 0 and (spy_pct >= 0 or dia_pct >= 0):
        return ScoreItem("科技股相对强弱", -1, "科技股单独弱", "QQQ 下跌但 SPY 或 DIA 仍能撑住，说明科技股单独承压。")
    if qqq_pct <= spy_pct - 0.5:
        return ScoreItem("科技股相对强弱", -1, "科技股相对弱", "QQQ 跑输 SPY 超过 0.5 个百分点。")
    if smh_pct is not None and smh_pct < qqq_pct:
        return ScoreItem("科技股相对强弱", -1, "芯片更弱", "SMH 弱于 QQQ，说明半导体链条压力更重。")
    if qqq_pct > spy_pct and qqq_pct > dia_pct:
        return ScoreItem("科技股相对强弱", 1, "科技股领涨", "QQQ 强于 SPY 和 DIA，纳指风险偏好仍在。")
    return ScoreItem("科技股相对强弱", 0, "中性", "科技股没有明显脱离大盘。")


def score_trend_shape(shape: str | None, close_position: float | None = None) -> ScoreItem:
    normalized = (shape or "unclear").lower().replace("_", " ")
    bearish = {"gap up fade", "selloff", "opened low kept falling", "rally faded", "close near low"}
    bullish = {"gap down rally", "v reversal", "opened high kept rising", "close near high"}
    if normalized in bearish:
        return ScoreItem("QQQ/NDX 昨晚走势", -1, "偏空", f"盘中形态为 {_cn_shape(shape)}。")
    if normalized in bullish:
        return ScoreItem("QQQ/NDX 昨晚走势", 1, "偏多", f"盘中形态为 {_cn_shape(shape)}。")
    if close_position is not None:
        if close_position <= 0.2:
            return ScoreItem("QQQ/NDX 昨晚走势", -1, "偏空", "收盘接近全天低位，尾盘承接偏弱。")
        if close_position >= 0.8:
            return ScoreItem("QQQ/NDX 昨晚走势", 1, "偏多", "收盘接近全天高位，尾盘承接较强。")
    return ScoreItem("QQQ/NDX 昨晚走势", 0, "中性", "盘中形态暂不清晰。")


def combine_scores(items: list[ScoreItem], cash_policy: CashPolicy | None = None) -> ScoreResult:
    policy = cash_policy or CashPolicy()
    total = sum(item.score for item in items)
    if total >= 3:
        trend = "strong bullish"
        model_buy = policy.normal_bullish_buy
        upside = 70
    elif total >= 1:
        trend = "bullish"
        model_buy = policy.normal_bullish_buy
        upside = 60
    elif total >= 0:
        trend = "range-bound"
        model_buy = policy.neutral_buy
        upside = 50
    elif total >= -1:
        trend = "range-bound"
        model_buy = policy.neutral_buy
        upside = 45
    elif total >= -3:
        trend = "bearish"
        model_buy = policy.bearish_buy
        upside = 35
    else:
        trend = "strong bearish"
        model_buy = policy.extreme_bearish_buy
        upside = 25

    available = max(0, min(policy.max_investable, policy.current_cash - policy.cash_floor))
    recommended = min(model_buy, available)
    strongest = max(items, key=lambda item: abs(item.score)).name if items else "none"
    rationale = "；".join(f"{item.name}：{item.label}（{item.score:+d}）" for item in items)
    return ScoreResult(
        items=tuple(items),
        total_score=total,
        trend_label=trend,
        upside_probability=upside,
        downside_probability=100 - upside,
        recommended_buy=recommended,
        key_variable=strongest,
        rationale=rationale,
    )


def _cn_shape(shape: str | None) -> str:
    return {
        "gap up fade": "高开低走",
        "selloff": "一路走弱",
        "opened low kept falling": "低开后继续走弱",
        "rally faded": "冲高回落",
        "close near low": "收盘接近最低点",
        "gap down rally": "低开高走",
        "v reversal": "V 型反转",
        "opened high kept rising": "高开后继续走强",
        "close near high": "收盘接近最高点",
    }.get(shape or "", shape or "不清晰")
