"""
SMU Meal Index - 抢饭指数计算引擎

两层输出：
  1. 逐节次人流统计 (hourly_flow)  -- 每个下课节次有多少人涌出
  2. 饭点抢饭指数   (meal_index)   -- 午饭 / 晚饭的 0-100 归一化分数 + 等级

归一化策略：
  - 冷启动（历史数据不足 ADAPTIVE_MIN_SAMPLES 天）：使用固定阈值 MIN_CROWD / MAX_CROWD
  - 正常运行：使用过去 ADAPTIVE_HISTORY_DAYS 天同餐次的 P10/P90 分位数作为动态阈值
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import database as db
from config import (
    ADAPTIVE_HISTORY_DAYS,
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


def _percentile(sorted_values: list[int], p: float) -> float:
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


def _get_adaptive_bounds(meal_type: str, campus: str, date: str) -> tuple[float, float]:
    """
    从历史数据计算自适应的归一化上下界。

    如果历史数据不足，回退到固定阈值。

    Returns
    -------
    (min_bound, max_bound)
    """
    history = db.query_head_counts_for_adaptive(
        meal_type=meal_type,
        campus=campus,
        before_date=date,
        days=ADAPTIVE_HISTORY_DAYS,
    )

    if len(history) < ADAPTIVE_MIN_SAMPLES:
        logger.info(
            "自适应归一化: %s %s 历史数据不足 (%d/%d)，使用固定阈值",
            campus,
            meal_type,
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

    logger.info(
        "自适应归一化: %s %s 基于 %d 天历史, P10=%.0f P90=%.0f",
        campus,
        meal_type,
        len(history),
        p10,
        p90,
    )
    return p10, p90


def _normalize_score(head_count: int, min_bound: float, max_bound: float) -> float:
    """将人数归一化到 0-100 分。"""
    if head_count <= min_bound:
        return 0.0
    if head_count >= max_bound:
        return 100.0
    return round((head_count - min_bound) / (max_bound - min_bound) * 100, 1)


def _score_to_level(score: float) -> str:
    """将分数映射到等级。"""
    for threshold, level in SCORE_LEVELS:
        if score <= threshold:
            return level
    return SCORE_LEVELS[-1][1]


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
    for course in courses:
        last_node = course.last_node
        node_counts[last_node] = node_counts.get(last_node, 0) + course.jxbrs

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

        # 累加饭点高峰节次的下课人数
        total = sum(flow_map.get(n, 0) for n in peak_nodes)

        # 取饭点最后一个节次的下课时间作为代表时间
        last_peak_node = peak_nodes[-1]
        end_time = timetable.get(last_peak_node, ("??:??", "??:??"))[1]

        # 自适应归一化
        min_bound, max_bound = _get_adaptive_bounds(meal_type, campus, date)
        score = _normalize_score(total, min_bound, max_bound)
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
            "%s - %s: %d 人, 得分 %.1f (%s) [阈值: %.0f-%.0f]",
            campus,
            meal_type,
            total,
            score,
            level,
            min_bound,
            max_bound,
        )

    return scores
