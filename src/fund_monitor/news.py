from __future__ import annotations

from dataclasses import dataclass


KEYWORDS = (
    "Fed",
    "FOMC",
    "Warsh",
    "Powell",
    "Treasury yields",
    "inflation",
    "CPI",
    "PPI",
    "PCE",
    "jobs",
    "unemployment",
    "jobless claims",
    "Nvidia",
    "Microsoft",
    "Apple",
    "Broadcom",
    "Tesla",
    "Meta",
    "AMD",
    "semiconductor",
    "AI chips",
    "oil",
    "Middle East",
    "Iran",
    "tariffs",
)


@dataclass(frozen=True)
class NewsImpact:
    event: str
    impact_path: str
    nasdaq_direction: str
    buy_change: str


def fallback_news_impacts() -> tuple[NewsImpact, ...]:
    return (
        NewsImpact(
            event="暂未配置实时新闻 API",
            impact_path="当前以期货、美债收益率、QQQ 相对强弱和宏观数据作为主要判断依据。",
            nasdaq_direction="未确认前按中性处理",
            buy_change="不要因为新闻源不可用而单独改变模型建议金额。",
        ),
    )
