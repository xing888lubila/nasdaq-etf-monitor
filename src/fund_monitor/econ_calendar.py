from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class EconEvent:
    name: str
    agency: str
    release_time_et: time
    importance: str
    impact_path: str


def is_near_830_et(now: datetime, window_minutes: int = 20) -> bool:
    eastern_now = now.astimezone(EASTERN) if now.tzinfo else now.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(EASTERN)
    target = eastern_now.replace(hour=8, minute=30, second=0, microsecond=0)
    return abs((eastern_now - target).total_seconds()) <= window_minutes * 60


def get_today_macro_events(now: datetime) -> list[EconEvent]:
    eastern_now = now.astimezone(EASTERN) if now.tzinfo else now.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(EASTERN)
    events: list[EconEvent] = []

    if eastern_now.weekday() == 3:
        events.append(
            EconEvent(
                name="Initial Jobless Claims",
                agency="U.S. Department of Labor",
                release_time_et=time(8, 30),
                importance="high",
                impact_path="初请低于预期，说明就业仍强，美联储压力可能上升，美债收益率可能上行，纳指估值承压。初请高于预期，说明就业降温，美债收益率可能回落，纳指获得缓和。",
            )
        )

    # Exact CPI/PPI/GDP/PCE dates vary by month. This job keeps the event trigger
    # time zone correct; add exact release dates through config or future parsers.
    return events


def describe_macro_preview(now: datetime) -> str:
    events = get_today_macro_events(now)
    if not events:
        return "今天暂未识别到内置的 8:30 ET 高重要性宏观数据。CPI、PPI、GDP、PCE、零售销售等需要以 BLS、DOL、BEA、Census 官方日历为准。"
    lines = []
    for event in events:
        lines.append(f"{event.name}（{event.agency}）发布时间 08:30 ET，重要性：{event.importance}。影响路径：{event.impact_path}")
    return "\n".join(lines)
