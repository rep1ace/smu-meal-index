"""
SMU Meal Index - 定时任务入口

用法：
    uv run python scheduler.py              # 抓取今天的数据
    uv run python scheduler.py 2026-03-09   # 抓取指定日期的数据

部署（GitHub Actions）：
    见 .github/workflows/update.yml

流程：登录 -> 抓取 -> 计算 -> 写入 SQLite -> 生成 data.json（含未来 6 天预测）
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
from zoneinfo import ZoneInfo

import database as db
import smu_login
from calculator import NodeFlow, compute_meal_scores, compute_node_flows
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


def _compute_stored_day_meals(
    date: str,
    campus: str,
    *,
    include_end_time: bool,
) -> dict:
    """基于已持久化的 hourly_flow，用当前算法回算某天某校区的饭点指数。"""
    hourly_rows = db.query_hourly(date, campus)
    if not hourly_rows:
        return {}

    node_flows = [
        NodeFlow(
            end_node=row["end_node"],
            end_time=row["end_time"],
            head_count=row["head_count"],
        )
        for row in hourly_rows
    ]

    result: dict = {}
    for ms in compute_meal_scores(node_flows, campus, date):
        payload = {
            "score": ms.score,
            "level": ms.level,
            "head_count": ms.head_count,
        }
        if include_end_time:
            payload["end_time"] = ms.end_time
        result[ms.meal_type] = payload
    return result


def _is_known_hourly_row(row: dict) -> bool:
    """判断逐节次人流是否有可识别作息时间。"""
    return row.get("end_time") != "??:??"


def _filter_known_hourly_rows(rows: list[dict]) -> list[dict]:
    """过滤作息表无法识别的节次，避免前端出现 ?? 时间。"""
    return [row for row in rows if _is_known_hourly_row(row)]


def _filter_forecast_hourly(forecast_hourly: dict) -> dict:
    """过滤预测逐节次人流中的未知作息时间。"""
    result: dict = {}
    for date, campuses in forecast_hourly.items():
        day_payload: dict = {}
        for campus, rows in campuses.items():
            known_rows = _filter_known_hourly_rows(rows)
            if known_rows:
                day_payload[campus] = known_rows
        if day_payload:
            result[date] = day_payload
    return result


def _compute_forecast(
    session,
    base_date: str,
    days: int = 6,
) -> tuple[dict, dict]:
    """
    抓取并计算未来 *days* 天的抢饭指数预测（不写入 SQLite）。

    Parameters
    ----------
    session : requests.Session
        已登录的 Session。
    base_date : str
        今天的日期 (YYYY-MM-DD)，预测从 base_date+1 开始。
    days : int
        预测天数，默认 6。

    Returns
    -------
    tuple[dict, dict]
        (forecast, forecast_hourly)

        forecast 结构：
        {
          "2026-03-08": {
            "本部": {
              "午饭": { score, level, head_count, end_time },
              "晚饭": { ... }
            },
            "顺德": { ... }
          },
          ...
        }

        forecast_hourly 结构：
        {
          "2026-03-08": {
            "本部": [ { end_node, end_time, head_count }, ... ],
            ...
          },
          ...
        }
    """
    forecast: dict = {}
    forecast_hourly: dict = {}

    base = datetime.date.fromisoformat(base_date)
    for offset in range(1, days + 1):
        future_date = (base + datetime.timedelta(days=offset)).isoformat()
        logger.info("预测: 抓取 %s 的课表 ...", future_date)

        try:
            all_courses = fetch_all_courses(session, future_date)
        except Exception as e:
            logger.warning("预测: 抓取 %s 失败: %s，跳过", future_date, e)
            continue

        total_courses = sum(len(v) for v in all_courses.values())
        if total_courses == 0:
            logger.info("预测: %s 无课程（可能是周末/假期）", future_date)
            continue

        day_meals: dict = {}
        day_hourly: dict = {}

        for campus, courses in all_courses.items():
            if not courses:
                continue

            node_flows = compute_node_flows(courses, campus)

            # 保存逐节次人流
            day_hourly[campus] = [
                {
                    "end_node": nf.end_node,
                    "end_time": nf.end_time,
                    "head_count": nf.head_count,
                }
                for nf in node_flows
            ]

            # 计算抢饭指数：使用预测日期本身判断同星期/工作日/周末历史口径
            meal_scores = compute_meal_scores(node_flows, campus, future_date)
            day_meals[campus] = {}
            for ms in meal_scores:
                day_meals[campus][ms.meal_type] = {
                    "score": ms.score,
                    "level": ms.level,
                    "head_count": ms.head_count,
                    "end_time": ms.end_time,
                }

        if day_meals:
            forecast[future_date] = day_meals
        if day_hourly:
            forecast_hourly[future_date] = day_hourly

    return forecast, forecast_hourly


def _build_data_json(
    date: str,
    forecast: dict | None = None,
    forecast_hourly: dict | None = None,
) -> dict:
    """
    构造供前端消费的 data.json 结构。

    包含：
      - today: 今天的饭点指数（按校区 -> 餐次）
      - hourly: 今天的逐节次人流（按校区 -> 列表）
      - history: 最近 7 天的饭点指数
      - forecast: 未来 6 天的抢饭指数预测（按日期 -> 校区 -> 餐次）
      - forecast_hourly: 未来 6 天的逐节次人流（按日期 -> 校区 -> 列表）
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
    for campus in list(today.keys()):
        recomputed = _compute_stored_day_meals(date, campus, include_end_time=True)
        if recomputed:
            today[campus] = recomputed

    # 今日逐节次人流
    hourly_rows = db.query_hourly(date)
    hourly: dict = {}
    for row in hourly_rows:
        if not _is_known_hourly_row(row):
            continue
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
    for d, campuses in history.items():
        for campus in list(campuses.keys()):
            recomputed = _compute_stored_day_meals(
                d,
                campus,
                include_end_time=False,
            )
            if recomputed:
                history[d][campus] = recomputed

    result = {
        "date": date,
        "updated_at": datetime.datetime.now(_BEIJING)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds"),
        "today": today,
        "hourly": hourly,
        "history": history,
    }

    if forecast:
        result["forecast"] = forecast
    if forecast_hourly:
        result["forecast_hourly"] = _filter_forecast_hourly(forecast_hourly)

    return result


def _write_data_json(
    date: str,
    forecast: dict | None = None,
    forecast_hourly: dict | None = None,
) -> None:
    """生成 web/data.json 文件。"""
    DATA_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _build_data_json(date, forecast, forecast_hourly)
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
    logger.info("[1/6] 登录教务系统 ...")
    session = smu_login.login()

    # 3. 抓取全校课表
    logger.info("[2/6] 抓取全校课表 ...")
    all_courses = fetch_all_courses(session, date)

    total_courses = sum(len(v) for v in all_courses.values())
    logger.info("全校共抓取 %d 条有效课程记录", total_courses)

    if total_courses == 0:
        logger.warning("今日无课程数据（可能是周末或假期），跳过计算")

    # 4. 计算指数并持久化（即使今日无课也继续，因为还需要预测未来）
    if total_courses > 0:
        logger.info("[3/6] 计算抢饭指数 ...")
        for campus, courses in all_courses.items():
            if not courses:
                logger.info("%s 校区无课程，跳过", campus)
                continue

            # 4a. 逐节次人流统计
            node_flows = compute_node_flows(courses, campus)
            db.delete_hourly_flows(date, campus)
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

        logger.info("[4/6] 数据已写入 SQLite")
    else:
        logger.info("[3/6] 今日无课程，跳过计算")
        logger.info("[4/6] 跳过 SQLite 写入")

    # 5. 计算未来 6 天预测
    logger.info("[5/6] 计算未来 6 天抢饭指数预测 ...")
    forecast, forecast_hourly = _compute_forecast(session, date, days=6)
    forecast_days = len(forecast)
    logger.info("预测完成: 共 %d 天有课程数据", forecast_days)

    # 6. 生成 data.json
    logger.info("[6/6] 生成 data.json ...")
    _write_data_json(date, forecast, forecast_hourly)

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

    if forecast:
        logger.info("--- 未来预测摘要 ---")
        for fdate in sorted(forecast.keys()):
            for campus, meals in forecast[fdate].items():
                for meal_type, data in meals.items():
                    logger.info(
                        "  %s %s %s: %.1f 分 (%s) | %d 人",
                        fdate,
                        campus,
                        meal_type,
                        data["score"],
                        data["level"],
                        data["head_count"],
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
