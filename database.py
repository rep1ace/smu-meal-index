"""
SMU Meal Index - SQLite 持久化模块

两张表：
  meal_index  - 饭点抢饭指数（核心表）
  hourly_flow - 逐节次人流明细
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Generator

from config import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
_CREATE_MEAL_INDEX = """
CREATE TABLE IF NOT EXISTS meal_index (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,
    campus      TEXT    NOT NULL,
    meal_type   TEXT    NOT NULL,
    score       REAL    NOT NULL,
    level       TEXT    NOT NULL,
    head_count  INTEGER NOT NULL,
    end_time    TEXT    NOT NULL,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, campus, meal_type)
);
"""

_CREATE_HOURLY_FLOW = """
CREATE TABLE IF NOT EXISTS hourly_flow (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,
    campus      TEXT    NOT NULL,
    end_node    INTEGER NOT NULL,
    end_time    TEXT    NOT NULL,
    head_count  INTEGER NOT NULL,
    UNIQUE(date, campus, end_node)
);
"""


# ---------------------------------------------------------------------------
# 连接管理
# ---------------------------------------------------------------------------


def init_db() -> None:
    """初始化数据库：创建表（如果不存在）。"""
    with _get_conn() as conn:
        conn.execute(_CREATE_MEAL_INDEX)
        conn.execute(_CREATE_HOURLY_FLOW)
        conn.commit()
    logger.info("数据库初始化完成: %s", DB_PATH)


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    """获取数据库连接的上下文管理器。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 写入操作
# ---------------------------------------------------------------------------


def upsert_meal_index(
    date: str,
    campus: str,
    meal_type: str,
    score: float,
    level: str,
    head_count: int,
    end_time: str,
) -> None:
    """插入或更新一条饭点抢饭指数记录。"""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO meal_index (date, campus, meal_type, score, level, head_count, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, campus, meal_type)
            DO UPDATE SET score=excluded.score,
                          level=excluded.level,
                          head_count=excluded.head_count,
                          end_time=excluded.end_time,
                          created_at=CURRENT_TIMESTAMP
            """,
            (date, campus, meal_type, score, level, head_count, end_time),
        )
        conn.commit()
    logger.debug("UPSERT meal_index: %s %s %s = %.1f", date, campus, meal_type, score)


def upsert_hourly_flow(
    date: str,
    campus: str,
    end_node: int,
    end_time: str,
    head_count: int,
) -> None:
    """插入或更新一条逐节次人流记录。"""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO hourly_flow (date, campus, end_node, end_time, head_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date, campus, end_node)
            DO UPDATE SET end_time=excluded.end_time,
                          head_count=excluded.head_count
            """,
            (date, campus, end_node, end_time, head_count),
        )
        conn.commit()
    logger.debug(
        "UPSERT hourly_flow: %s %s node=%d count=%d", date, campus, end_node, head_count
    )


def delete_hourly_flows(date: str, campus: str) -> None:
    """删除某天某校区的逐节次人流，用于重跑时清理旧节点。"""
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM hourly_flow WHERE date = ? AND campus = ?",
            (date, campus),
        )
        conn.commit()
    logger.debug("DELETE hourly_flow: %s %s", date, campus)


# ---------------------------------------------------------------------------
# 查询操作
# ---------------------------------------------------------------------------


def query_today(date: str) -> list[dict[str, Any]]:
    """查询指定日期所有校区的饭点指数。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT date, campus, meal_type, score, level, head_count, end_time "
            "FROM meal_index WHERE date = ? ORDER BY campus, meal_type",
            (date,),
        ).fetchall()
    return [dict(r) for r in rows]


def query_today_campus(date: str, campus: str) -> list[dict[str, Any]]:
    """查询指定日期、指定校区的饭点指数。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT date, campus, meal_type, score, level, head_count, end_time "
            "FROM meal_index WHERE date = ? AND campus = ? ORDER BY meal_type",
            (date, campus),
        ).fetchall()
    return [dict(r) for r in rows]


def query_history(campus: str | None = None, days: int = 7) -> list[dict[str, Any]]:
    """查询最近 N 天的历史指数。"""
    with _get_conn() as conn:
        if campus:
            rows = conn.execute(
                "SELECT date, campus, meal_type, score, level, head_count, end_time "
                "FROM meal_index WHERE campus = ? "
                "ORDER BY date DESC, meal_type "
                "LIMIT ?",
                (campus, days * 2),  # 每天 2 条（午饭+晚饭）
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT date, campus, meal_type, score, level, head_count, end_time "
                "FROM meal_index "
                "ORDER BY date DESC, campus, meal_type "
                "LIMIT ?",
                (days * 4,),  # 每天 4 条（2 校区 x 2 餐）
            ).fetchall()
    return [dict(r) for r in rows]


def query_hourly(date: str, campus: str | None = None) -> list[dict[str, Any]]:
    """查询指定日期的逐节次人流明细。"""
    with _get_conn() as conn:
        if campus:
            rows = conn.execute(
                "SELECT date, campus, end_node, end_time, head_count "
                "FROM hourly_flow WHERE date = ? AND campus = ? ORDER BY end_node",
                (date, campus),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT date, campus, end_node, end_time, head_count "
                "FROM hourly_flow WHERE date = ? ORDER BY campus, end_node",
                (date,),
            ).fetchall()
    return [dict(r) for r in rows]


def query_head_counts_for_adaptive(
    meal_type: str, campus: str, before_date: str, days: int
) -> list[int]:
    """
    查询指定餐次、校区在 before_date 之前 days 天内的 head_count 列表，
    用于自适应归一化。
    """
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT head_count FROM meal_index "
            "WHERE meal_type = ? AND campus = ? AND date < ? "
            "ORDER BY date DESC LIMIT ?",
            (meal_type, campus, before_date, days),
        ).fetchall()
    return [r["head_count"] for r in rows]


def query_weighted_pressures_for_adaptive(
    meal_type: str,
    campus: str,
    before_date: str,
    days: int,
    node_weights: dict[int, float],
    *,
    sqlite_weekday: str | None = None,
    weekend: bool | None = None,
) -> list[float]:
    """
    查询历史饭点加权压力值，用于自适应归一化。

    历史日期来自 meal_index，具体压力值由 hourly_flow 的节次人流按
    node_weights 加权重算。即使某天没有对应节次人流，也保留为 0，
    避免低课日被静默丢弃。
    """
    if not node_weights:
        return []
    if sqlite_weekday is not None and weekend is not None:
        raise ValueError("sqlite_weekday and weekend cannot be used together")

    where_parts = [
        "meal_type = ?",
        "campus = ?",
        "date < ?",
    ]
    params: list[Any] = [meal_type, campus, before_date]

    if sqlite_weekday is not None:
        where_parts.append("strftime('%w', date) = ?")
        params.append(sqlite_weekday)
    elif weekend is True:
        where_parts.append("strftime('%w', date) IN ('0', '6')")
    elif weekend is False:
        where_parts.append("strftime('%w', date) NOT IN ('0', '6')")

    where_sql = " AND ".join(where_parts)

    with _get_conn() as conn:
        date_rows = conn.execute(
            f"SELECT date FROM meal_index WHERE {where_sql} "
            "ORDER BY date DESC LIMIT ?",
            (*params, days),
        ).fetchall()
        dates = [r["date"] for r in date_rows]
        if not dates:
            return []

        date_placeholders = ",".join("?" for _ in dates)
        node_placeholders = ",".join("?" for _ in node_weights)
        rows = conn.execute(
            f"SELECT date, end_node, head_count FROM hourly_flow "
            f"WHERE campus = ? "
            f"AND date IN ({date_placeholders}) "
            f"AND end_node IN ({node_placeholders})",
            (campus, *dates, *node_weights.keys()),
        ).fetchall()

    pressure_by_date = dict.fromkeys(dates, 0.0)
    for row in rows:
        weight = node_weights.get(row["end_node"], 0.0)
        pressure_by_date[row["date"]] += row["head_count"] * weight

    return list(pressure_by_date.values())


def query_recent_days(days: int) -> list[dict[str, Any]]:
    """查询最近 N 天的所有 meal_index 记录（按日期降序）。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM meal_index ORDER BY date DESC LIMIT ?",
            (days,),
        ).fetchall()
        if not rows:
            return []
        dates = [r["date"] for r in rows]
        placeholders = ",".join("?" for _ in dates)
        records = conn.execute(
            f"SELECT date, campus, meal_type, score, level, head_count, end_time "
            f"FROM meal_index WHERE date IN ({placeholders}) "
            f"ORDER BY date DESC, campus, meal_type",
            dates,
        ).fetchall()
    return [dict(r) for r in records]


def query_recent_hourly(days: int) -> list[dict[str, Any]]:
    """查询最近 N 天的所有 hourly_flow 记录。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM hourly_flow ORDER BY date DESC LIMIT ?",
            (days,),
        ).fetchall()
        if not rows:
            return []
        dates = [r["date"] for r in rows]
        placeholders = ",".join("?" for _ in dates)
        records = conn.execute(
            f"SELECT date, campus, end_node, end_time, head_count "
            f"FROM hourly_flow WHERE date IN ({placeholders}) "
            f"ORDER BY date DESC, campus, end_node",
            dates,
        ).fetchall()
    return [dict(r) for r in records]
