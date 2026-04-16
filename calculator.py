"""
SMU Meal Index - 抢饭指数计算引擎

两层输出：
  1. 逐节次人流统计 (hourly_flow)  -- 每个下课节次有多少人涌出
  2. 饭点抢饭指数   (meal_index)   -- 午饭 / 晚饭的 0-100 归一化分数 + 等级

归一化策略：
  - 饭点压力值：后一节下课人数 + 较早一节下课人数 * 时间衰减权重
  - 冷启动（历史数据不足 ADAPTIVE_MIN_SAMPLES 天）：使用固定阈值 MIN_CROWD / MAX_CROWD
  - 正常运行：优先使用同星期历史，其次同日类型（工作日/周末），再回退全量历史的 P10/P90
  - 最小阈值跨度：避免低课日 P10/P90 过窄，把几十人的小波动放大成拥挤
  - 绝对压力下限：实际人流不小时，不让相对历史低位被硬压成 0 分
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

import database as db
from config import (
    ABSOLUTE_PRESSURE_FLOOR_FACTOR,
    ADAPTIVE_HISTORY_DAYS,
    ADAPTIVE_MIN_SPAN,
    ADAPTIVE_MIN_SAMPLES,
    MAX_CROWD,
    MEAL_PERIODS,
    MIN_CROWD,
    SCORE_LEVELS,
    TIMETABLE,
)
from fetcher import CourseRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class NodeFlow:
    """某个下课节次的人流统计。"""

    end_node: int  # 下课节次号
    end_time: str  # 下课时间 (HH:MM)
    head_count: int  # 该节次下课的总人数


@dataclass
class MealScore:
    """某个饭点的抢饭指数。"""

    meal_type: str  # "午饭" / "晚饭"
    score: float  # 0 - 100 归一化分数
    level: str  # "畅通" / "一般" / "拥挤" / "爆满"
    head_count: int  # 饭点前下课总人数
    end_time: str  # 该饭点最后一节课的下课时间


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------


def _percentile(sorted_values: list[float], p: float) -> float:
    """计算已排序列表的第 p 百分位数（0-100）。"""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (p / 100) * (n - 1)
    f = int(k)
    c = f + 1
    if c >= n:
        return float(sorted_values[-1])
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def _sqlite_weekday(date: str) -> str:
    """返回与 SQLite strftime('%w') 一致的星期值：周日=0，周六=6。"""
    weekday = datetime.date.fromisoformat(date).weekday()  # 周一=0
    return str((weekday + 1) % 7)


def _query_pressure_history(
    meal_type: str,
    campus: str,
    date: str,
    node_weights: dict[int, float],
) -> tuple[list[float], str]:
    """
    按“同星期 -> 同日类型 -> 全量”的优先级获取历史压力值。

    同星期样本不足时，用工作日/周末分组避免低课日把工作日阈值拉低。
    """
    sqlite_wday = _sqlite_weekday(date)
    is_weekend = sqlite_wday in {"0", "6"}

    attempts = [
        ("同星期", {"sqlite_weekday": sqlite_wday}),
        ("周末" if is_weekend else "工作日", {"weekend": is_weekend}),
        ("全量", {}),
    ]

    fallback_history: list[float] = []
    fallback_label = "全量"
    for label, filters in attempts:
        history = db.query_weighted_pressures_for_adaptive(
            meal_type=meal_type,
            campus=campus,
            before_date=date,
            days=ADAPTIVE_HISTORY_DAYS,
            node_weights=node_weights,
            **filters,
        )
        if history and not fallback_history:
            fallback_history = history
            fallback_label = label
        if len(history) >= ADAPTIVE_MIN_SAMPLES:
            return history, label

    return fallback_history, fallback_label


def _get_adaptive_bounds(
    meal_type: str,
    campus: str,
    date: str,
    node_weights: dict[int, float],
) -> tuple[float, float]:
    """
    从历史数据计算自适应的归一化上下界。

    如果历史数据不足，回退到固定阈值。

    Returns
    -------
    (min_bound, max_bound)
    """
    history, history_scope = _query_pressure_history(
        meal_type=meal_type,
        campus=campus,
        date=date,
        node_weights=node_weights,
    )

    if len(history) < ADAPTIVE_MIN_SAMPLES:
        logger.info(
            "自适应归一化: %s %s %s历史压力样本不足 (%d/%d)，使用固定阈值",
            campus,
            meal_type,
            history_scope,
            len(history),
            ADAPTIVE_MIN_SAMPLES,
        )
        return float(MIN_CROWD), float(MAX_CROWD)

    sorted_h = sorted(history)
    p10 = _percentile(sorted_h, 10)
    p90 = _percentile(sorted_h, 90)

    # 防止 p10 == p90 导致除零
    if p90 <= p10:
        p90 = p10 + 1.0
    if p90 - p10 < ADAPTIVE_MIN_SPAN:
        p90 = p10 + float(ADAPTIVE_MIN_SPAN)

    logger.info(
        "自适应归一化: %s %s 基于 %s %d 天历史压力, P10=%.0f P90=%.0f",
        campus,
        meal_type,
        history_scope,
        len(history),
        p10,
        p90,
    )
    return p10, p90


def _normalize_score(value: float, min_bound: float, max_bound: float) -> float:
    """将压力值归一化到 0-100 分。"""
    if value <= min_bound:
        return 0.0
    if value >= max_bound:
        return 100.0
    return round((value - min_bound) / (max_bound - min_bound) * 100, 1)


def _score_to_level(score: float) -> str:
    """将分数映射到等级。"""
    for threshold, level in SCORE_LEVELS:
        if score <= threshold:
            return level
    return SCORE_LEVELS[-1][1]


def _apply_absolute_pressure_floor(adaptive_score: float, pressure: float) -> float:
    """
    给自适应分数加一个绝对压力下限。

    这样低于历史 P10 的工作日不会直接变成 0，但周末/空课日仍然保持低分。
    """
    absolute_score = _normalize_score(pressure, float(MIN_CROWD), float(MAX_CROWD))
    floor_score = absolute_score * ABSOLUTE_PRESSURE_FLOOR_FACTOR
    return round(max(adaptive_score, floor_score), 1)


def _compute_weighted_pressure(
    flow_map: dict[int, int],
    node_weights: dict[int, float],
) -> float:
    """根据节次权重计算饭点压力值。"""
    return sum(flow_map.get(node, 0) * weight for node, weight in node_weights.items())


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def compute_node_flows(
    courses: list[CourseRecord],
    campus: str,
) -> list[NodeFlow]:
    """
    统计每个下课节次的总人数。

    Parameters
    ----------
    courses : list[CourseRecord]
        某校区某天的全部课程。
    campus : str
        校区名（用于查找作息时间表）。

    Returns
    -------
    list[NodeFlow]
        按节次排序的人流统计列表。
    """
    timetable = TIMETABLE[campus]

    # 按下课节次聚合人数
    node_counts: dict[int, int] = {}
    invalid_node_counts: dict[int, int] = {}
    for course in courses:
        last_node = course.last_node
        if last_node not in timetable:
            invalid_node_counts[last_node] = (
                invalid_node_counts.get(last_node, 0) + course.jxbrs
            )
            continue
        node_counts[last_node] = node_counts.get(last_node, 0) + course.jxbrs

    if invalid_node_counts:
        logger.warning(
            "%s 存在作息表未定义节次，已从逐节次统计中过滤: %s",
            campus,
            dict(sorted(invalid_node_counts.items())),
        )

    # 构造 NodeFlow 列表
    flows: list[NodeFlow] = []
    for node in sorted(node_counts.keys()):
        end_time = timetable.get(node, ("??:??", "??:??"))[1]  # 取结束时间
        flows.append(
            NodeFlow(
                end_node=node,
                end_time=end_time,
                head_count=node_counts[node],
            )
        )

    return flows


def compute_meal_scores(
    node_flows: list[NodeFlow],
    campus: str,
    date: str,
) -> list[MealScore]:
    """
    计算午饭和晚饭的抢饭指数。

    使用自适应归一化：基于历史同餐次数据的 P10/P90 分位数。
    历史数据不足时回退到固定阈值。

    Parameters
    ----------
    node_flows : list[NodeFlow]
        逐节次人流统计（来自 compute_node_flows）。
    campus : str
        校区名。
    date : str
        当前日期 (YYYY-MM-DD)，用于查询历史数据。

    Returns
    -------
    list[MealScore]
        午饭和晚饭各一个 MealScore。
    """
    timetable = TIMETABLE[campus]

    # 建立 node -> head_count 快速查找
    flow_map: dict[int, int] = {nf.end_node: nf.head_count for nf in node_flows}

    scores: list[MealScore] = []
    for meal_type, cfg in MEAL_PERIODS.items():
        peak_nodes: list[int] = cfg["peak_nodes"]
        node_weights: dict[int, float] = cfg.get(
            "node_weights",
            {node: 1.0 for node in peak_nodes},
        )

        # 累加饭点高峰节次的下课人数
        total = sum(flow_map.get(n, 0) for n in peak_nodes)
        pressure = _compute_weighted_pressure(flow_map, node_weights)

        # 取饭点最后一个节次的下课时间作为代表时间
        last_peak_node = peak_nodes[-1]
        end_time = timetable.get(last_peak_node, ("??:??", "??:??"))[1]

        # 自适应归一化
        min_bound, max_bound = _get_adaptive_bounds(
            meal_type,
            campus,
            date,
            node_weights,
        )
        adaptive_score = _normalize_score(pressure, min_bound, max_bound)
        score = _apply_absolute_pressure_floor(adaptive_score, pressure)
        level = _score_to_level(score)

        scores.append(
            MealScore(
                meal_type=meal_type,
                score=score,
                level=level,
                head_count=total,
                end_time=end_time,
            )
        )

        logger.info(
            "%s - %s: %d 人, 压力 %.1f, 得分 %.1f (%s) [自适应 %.1f, 阈值: %.0f-%.0f]",
            campus,
            meal_type,
            total,
            pressure,
            score,
            level,
            adaptive_score,
            min_bound,
            max_bound,
        )

    return scores
