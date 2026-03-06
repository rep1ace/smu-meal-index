"""
SMU Meal Index - 全校课表抓取模块
通过 paginateQxkb 接口分页获取指定日期、指定校区的全部课程。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from config import CAMPUSES, EXCLUDED_JXHJ, XNXQDM, ZHJW_HEADERS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 接口地址
# ---------------------------------------------------------------------------
QXKB_URL = "https://zhjw.smu.edu.cn/new/student/xsgrkb/paginateQxkb"

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class CourseRecord:
    """一条课程排课记录。"""

    kcmc: str  # 课程名称
    teaxms: str  # 教师姓名
    jxcdmc: str  # 教学场地名称（如 "607教室"）
    jxhjmc: str  # 教学环节（理论/实验/自主学习）
    jcdm: str  # 节次代码（如 "0809" = 第8-9节）
    jxbrs: int  # 教学班人数
    pkrs: int  # 排课人数
    pkrq: str  # 排课日期
    xqmc: str  # 校区名称
    campus: str  # 校区标识（"本部" / "顺德"）

    @property
    def last_node(self) -> int:
        """
        从 jcdm 中提取最后一个节次号。

        jcdm 每 2 位代表一个节次：
          "0809"    -> [8, 9]   -> 最后节次 = 9
          "030405"  -> [3, 4, 5] -> 最后节次 = 5
        """
        return int(self.jcdm[-2:])

    @property
    def all_nodes(self) -> list[int]:
        """解析 jcdm 中的所有节次号。"""
        nodes = []
        for i in range(0, len(self.jcdm), 2):
            nodes.append(int(self.jcdm[i : i + 2]))
        return nodes


def _parse_row(row: dict[str, Any], campus: str) -> CourseRecord:
    """将接口返回的一行 JSON 解析为 CourseRecord。"""
    return CourseRecord(
        kcmc=row.get("kcmc", ""),
        teaxms=row.get("teaxms", ""),
        jxcdmc=row.get("jxcdmc", ""),
        jxhjmc=row.get("jxhjmc", ""),
        jcdm=str(row.get("jcdm", "")),
        jxbrs=int(row.get("jxbrs", 0)),
        pkrs=int(row.get("pkrs", 0)),
        pkrq=row.get("pkrq", ""),
        xqmc=row.get("xqmc", ""),
        campus=campus,
    )


# ---------------------------------------------------------------------------
# 抓取逻辑
# ---------------------------------------------------------------------------


def fetch_campus_courses(
    session: requests.Session,
    date: str,
    campus: str,
    rows_per_page: int = 60,
) -> list[CourseRecord]:
    """
    抓取指定校区、指定日期的全部课程。

    Parameters
    ----------
    session : requests.Session
        已登录的 Session。
    date : str
        目标日期，格式 "YYYY-MM-DD"。
    campus : str
        校区标识："本部" 或 "顺德"。
    rows_per_page : int
        每页条数，默认 60。

    Returns
    -------
    list[CourseRecord]
        过滤后的课程列表（已排除自主学习，已筛选教学场地）。
    """
    campus_cfg = CAMPUSES[campus]
    xqdm = campus_cfg["xqdm"]
    building_kw = campus_cfg["building_keyword"]

    all_records: list[CourseRecord] = []
    page = 1

    while True:
        payload = {
            "xnxqdm": XNXQDM,
            "xqdm": xqdm,
            "zc": "",
            "xq": "",
            "kcdm": "",
            "kkyxdm": "",
            "kkjysdm": "",
            "jcdm": "",
            "gnqdm": "",
            "rq": date,
            "jzwdm": "",
            "kcrwdm": "",
            "teaxm": "",
            "jhlxdm": "",
            "queryParams[primarySort]": " dgksdm asc",
            "page": page,
            "rows": rows_per_page,
            "sort": "kxh",
            "order": "asc",
        }

        logger.info("抓取 %s 校区 %s 第 %d 页 ...", campus, date, page)
        resp = session.post(QXKB_URL, data=payload, headers=ZHJW_HEADERS)
        resp.raise_for_status()
        data = resp.json()

        rows = data.get("rows", [])
        if not rows:
            break

        for row in rows:
            record = _parse_row(row, campus)

            # 过滤：排除自主学习
            if record.jxhjmc in EXCLUDED_JXHJ:
                continue

            # 过滤：只保留目标教学场馆的课程
            if building_kw not in record.jxcdmc:
                continue

            all_records.append(record)

        # 如果返回条数不足一页，说明已经到最后一页
        if len(rows) < rows_per_page:
            break

        page += 1

    logger.info(
        "%s 校区 %s 共获取 %d 条有效课程记录",
        campus,
        date,
        len(all_records),
    )
    return all_records


def fetch_all_courses(
    session: requests.Session,
    date: str,
) -> dict[str, list[CourseRecord]]:
    """
    抓取所有校区指定日期的课程。

    Returns
    -------
    dict[str, list[CourseRecord]]
        key = 校区名（"本部" / "顺德"），value = 该校区的课程列表。
    """
    result: dict[str, list[CourseRecord]] = {}
    for campus in CAMPUSES:
        result[campus] = fetch_campus_courses(session, date, campus)
    return result
