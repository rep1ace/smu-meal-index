"""
SMU Meal Index - 定时任务入口

用法：
    uv run python scheduler.py              # 抓取今天的数据
    uv run python scheduler.py 2026-03-09   # 抓取指定日期的数据

部署（GitHub Actions）：
    见 .github/workflows/update.yml

流程：登录 -> 抓取 -> 计算 -> 写入 SQLite -> 生成 data.json
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
from zoneinfo import ZoneInfo

import database as db
import smu_login
from calculator import compute_meal_scores, compute_node_flows
from config import DATA_JSON_PATH
from fetcher import fetch_all_courses

# 北京时间时区
_BEIJING = ZoneInfo("Asia/Shanghai")

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

# ---------------------------------------------------------------------------
# data.json 生成
# ---------------------------------------------------------------------------


def _build_data_json(date: str) -> dict:
    """
    构造供前端消费的 data.json 结构。

    包含：
      - today: 今天的饭点指数（按校区 -> 餐次）
      - hourly: 今天的逐节次人流（按校区 -> 列表）
      - history: 最近 7 天的饭点指数
    """
    # 今日指数
    today_rows = db.query_today(date)
    today: dict = {}
    for row in today_rows:
        campus = row["campus"]
        meal_type = row["meal_type"]
        if campus not in today:
            today[campus] = {}
        today[campus][meal_type] = {
            "score": row["score"],
            "level": row["level"],
            "head_count": row["head_count"],
            "end_time": row["end_time"],
        }

    # 今日逐节次人流
    hourly_rows = db.query_hourly(date)
    hourly: dict = {}
    for row in hourly_rows:
        campus = row["campus"]
        if campus not in hourly:
            hourly[campus] = []
        hourly[campus].append(
            {
                "end_node": row["end_node"],
                "end_time": row["end_time"],
                "head_count": row["head_count"],
            }
        )

    # 最近 7 天历史
    history_rows = db.query_recent_days(7)
    history: dict = {}
    for row in history_rows:
        d = row["date"]
        if d not in history:
            history[d] = {}
        campus = row["campus"]
        if campus not in history[d]:
            history[d][campus] = {}
        history[d][campus][row["meal_type"]] = {
            "score": row["score"],
            "level": row["level"],
            "head_count": row["head_count"],
        }

    return {
        "date": date,
        "updated_at": datetime.datetime.now(_BEIJING)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds"),
        "today": today,
        "hourly": hourly,
        "history": history,
    }


def _write_data_json(date: str) -> None:
    """生成 web/data.json 文件。"""
    DATA_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _build_data_json(date)
    with open(DATA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("data.json 已写入: %s", DATA_JSON_PATH)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run(date: str | None = None) -> None:
    """
    完整的 抓取-计算-持久化-发布 流水线。

    Parameters
    ----------
    date : str, optional
        目标日期 (YYYY-MM-DD)。默认为今天。
    """
    if date is None:
        date = datetime.datetime.now(_BEIJING).date().isoformat()

    logger.info("========== SMU Meal Index 开始运行 ==========")
    logger.info("目标日期: %s", date)

    # 1. 初始化数据库
    db.init_db()

    # 2. 登录教务系统
    logger.info("[1/5] 登录教务系统 ...")
    session = smu_login.login()

    # 3. 抓取全校课表
    logger.info("[2/5] 抓取全校课表 ...")
    all_courses = fetch_all_courses(session, date)

    total_courses = sum(len(v) for v in all_courses.values())
    logger.info("全校共抓取 %d 条有效课程记录", total_courses)

    if total_courses == 0:
        logger.warning("今日无课程数据（可能是周末或假期），跳过计算")
        # 即使无数据也生成 data.json（前端可显示"今日无课"）
        _write_data_json(date)
        return

    # 4. 计算指数并持久化
    logger.info("[3/5] 计算抢饭指数 ...")
    for campus, courses in all_courses.items():
        if not courses:
            logger.info("%s 校区无课程，跳过", campus)
            continue

        # 4a. 逐节次人流统计
        node_flows = compute_node_flows(courses, campus)
        for nf in node_flows:
            db.upsert_hourly_flow(
                date=date,
                campus=campus,
                end_node=nf.end_node,
                end_time=nf.end_time,
                head_count=nf.head_count,
            )

        # 4b. 饭点抢饭指数（使用自适应归一化）
        meal_scores = compute_meal_scores(node_flows, campus, date)
        for ms in meal_scores:
            db.upsert_meal_index(
                date=date,
                campus=campus,
                meal_type=ms.meal_type,
                score=ms.score,
                level=ms.level,
                head_count=ms.head_count,
                end_time=ms.end_time,
            )

    logger.info("[4/5] 数据已写入 SQLite")

    # 5. 生成 data.json
    logger.info("[5/5] 生成 data.json ...")
    _write_data_json(date)

    logger.info("========== SMU Meal Index 运行完成 ==========")

    # 打印摘要
    today_data = db.query_today(date)
    if today_data:
        logger.info("--- 今日抢饭指数摘要 ---")
        for row in today_data:
            logger.info(
                "  %s %s: %.1f 分 (%s) | %d 人 | 下课时间 %s",
                row["campus"],
                row["meal_type"],
                row["score"],
                row["level"],
                row["head_count"],
                row["end_time"],
            )


def main() -> None:
    """命令行入口。"""
    date = None
    if len(sys.argv) > 1:
        date = sys.argv[1]
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            print(f"错误: 日期格式不正确，请使用 YYYY-MM-DD 格式。收到: {date}")
            sys.exit(1)

    try:
        run(date)
    except Exception as e:
        logger.error("运行失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
