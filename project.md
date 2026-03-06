# SMU Meal Index - 项目规划文档

> 本文档作为项目上下文的完整记录，便于更换模型/Agent时无缝衔接。

## 一、项目概述

**项目名称**：SMU Meal Index（南方医科大学抢饭指数）

**目标**：脚本自动登录教务处，抓取全校当日课表，提取每节课的学生人数，计算上午/下午饭点前在教学楼中的总人数，生成"抢饭指数"并持久化到 SQLite，生成静态 `data.json` 文件供前端读取。

**基于**：[WakeUp4SMU](https://github.com/rep1ace/WakeUp4SMU) 的自动登录逻辑（`auto_update.py` + `smulogin.py`）。

**部署方式**：VPS cron 定时运行抓取脚本 → 计算 → 写 SQLite → 生成 `web/data.json` → `git push`。Vercel 部署 `web/` 目录作为静态站点，前端直接读取 `data.json`。服务器为 1C1G 配置，无需常驻进程。

---

## 二、校区与教学场馆

| 校区     | 校区代码 (xqdm) | 教学场馆关键词 | 说明                                     |
| -------- | --------------- | -------------- | ---------------------------------------- |
| 校本部   | `00001`       | `教室`       | jxcdmc 中包含"教室"的课程（如"607教室"） |
| 顺德校区 | `00009`       | 教室           | jxcdmc 中包含"教室"的课程                |

---

## 三、核心接口信息

### 3.1 登录流程（UIS 统一认证）

1. **获取验证码**：`GET https://uis.smu.edu.cn/imageServlet.do` → 图片
2. **OCR 识别**：使用 `ddddocr` 自动识别验证码（无需人工输入）
3. **发送登录请求**：`POST https://uis.smu.edu.cn/login/login.do`
   - `loginName`: 学号
   - `password`: MD5(密码)
   - `randcodekey`: 验证码
   - `appid`: `3550176`
   - `redirect`: `https://zhjw.smu.edu.cn/new/ssoLogin`
   - 返回 JSON，成功时包含 `ticket`
4. **SSO 跳转**：`GET https://zhjw.smu.edu.cn/new/ssoLogin?ticket=xxx`
5. **重试机制**：验证码识别可能失败，最多重试 5 次

### 3.2 全校课表抓取接口

```
POST https://zhjw.smu.edu.cn/new/student/xsgrkb/paginateQxkb

参数：
  xnxqdm    = 202502          # 学年学期代码（硬编码）
  xqdm      = 00001 / 00002   # 校区代码
  rq        = 2026-03-09      # 目标日期（YYYY-MM-DD 格式）
  page      = 1, 2, 3...      # 分页页码
  rows      = 60              # 每页条数
  sort      = kxh
  order     = asc
  zc        =                 # 留空
  xq        =                 # 留空
  kcdm      =                 # 留空
  kkyxdm    =                 # 留空
  kkjysdm   =                 # 留空
  jcdm      =                 # 留空
  gnqdm     =                 # 留空
  jzwdm     =                 # 留空
  kcrwdm    =                 # 留空
  teaxm     =                 # 留空
  jhlxdm    =                 # 留空
  queryParams[primarySort] = dgksdm asc
```

### 3.3 返回数据示例

```json
{
  "rows": [
    {
      "teaxms": "徐静涛",
      "jxbmc": "2022法医学",
      "pkrs": 43,
      "jxbrs": 42,
      "zc": 2,
      "jxhjmc": "理论",
      "jxcdmc": "607教室",
      "pkrq": "2026-03-09",
      "jcdm": "0809",
      "xqmc": "校本部",
      "xq": 1,
      "kcmc": "法医临床学"
    }
  ]
}
```

### 3.4 关键字段说明

| 字段       | 含义         | 用途                                                                    |
| ---------- | ------------ | ----------------------------------------------------------------------- |
| `jxbrs`  | 教学班人数   | **核心**：用于计算人数                                            |
| `pkrs`   | 排课人数     | 参考，优先使用 jxbrs                                                    |
| `jcdm`   | 节次代码     | 如 `"0809"` = 第8-9节；`"030405"` = 第3-5节；每两位数字代表一个节次 |
| `jxhjmc` | 教学环节名称 | **过滤**：`"自主学习"` 需排除（学生在宿舍不到教室）             |
| `jxcdmc` | 教学场地名称 | **过滤**：本部只保留含"教室"的，顺德只保留含"春华堂"的            |
| `pkrq`   | 排课日期     | 用于校验                                                                |
| `xqmc`   | 校区名称     | 信息参考                                                                |
| `kcmc`   | 课程名称     | 信息展示                                                                |
| `teaxms` | 教师姓名     | 信息展示                                                                |

---

## 四、作息时间表

### 本部（timetable type 1）

| 节次 | 开始时间 | 结束时间 |
| ---- | -------- | -------- |
| 1    | 08:00    | 08:40    |
| 2    | 08:45    | 09:25    |
| 3    | 09:50    | 10:30    |
| 4    | 10:35    | 11:15    |
| 5    | 11:20    | 12:00    |
| 6    | 14:30    | 15:10    |
| 7    | 15:15    | 15:55    |
| 8    | 16:15    | 16:55    |
| 9    | 17:00    | 17:40    |
| 10   | 19:30    | 20:10    |
| 11   | 20:30    | 21:10    |

### 顺德校区（timetable type 2）

| 节次 | 开始时间 | 结束时间 |
| ---- | -------- | -------- |
| 1    | 08:30    | 09:10    |
| 2    | 09:15    | 09:55    |
| 3    | 10:20    | 11:00    |
| 4    | 11:05    | 11:45    |
| 5    | 11:50    | 12:30    |
| 6    | 14:00    | 14:40    |
| 7    | 14:45    | 15:25    |
| 8    | 15:45    | 16:25    |
| 9    | 16:30    | 17:10    |
| 10   | 19:30    | 20:10    |
| 11   | 20:30    | 21:10    |

---

## 五、抢饭指数计算逻辑

### 5.1 jcdm 解析

`jcdm` 字段每 2 位代表一个节次。例如：

- `"0809"` → 第 8、9 节 → 最后一节 = 9
- `"030405"` → 第 3、4、5 节 → 最后一节 = 5
- `"01020304"` → 第 1、2、3、4 节 → 最后一节 = 4

提取方式：`last_node = int(jcdm[-2:])`

### 5.2 逐节次人流统计

对当日所有课程（已过滤），按"最后一节的节次号"分组，累加 `jxbrs`：

```
node_flow = {
    1: 0, 2: 120, 3: 0, 4: 350, 5: 980,
    6: 0, 7: 200, 8: 150, 9: 620,
    10: 0, 11: 80
}
```

含义：第 5 节下课时共有 980 人涌出教学楼。

### 5.3 饭点抢饭指数

**午饭高峰节次**：第 4、5 节（本部 11:15 / 12:00，顺德 11:45 / 12:30）
**晚饭高峰节次**：第 8、9 节（本部 16:55 / 17:40，顺德 16:25 / 17:10）

```
午饭下课总人数 = node_flow[4] + node_flow[5]
晚饭下课总人数 = node_flow[8] + node_flow[9]
```

### 5.4 归一化（0-100 分）

采用**自适应归一化**：使用过去 30 天同校区同餐次的 P10/P90 分位数作为动态阈值。

当历史数据不足 7 天时，回退到固定阈值：

```python
MIN_CROWD = 0       # 最低人数基准
MAX_CROWD = 3000    # 最高人数基准（可配置）

score = min(100, max(0, (head_count - MIN_CROWD) / (MAX_CROWD - MIN_CROWD) * 100))
```

### 5.5 指数等级

| 分数区间 | 等级 | 含义             |
| -------- | ---- | ---------------- |
| 0 - 25   | 畅通 | 食堂很空，随便吃 |
| 25 - 50  | 一般 | 正常排队         |
| 50 - 75  | 拥挤 | 需要抢位置       |
| 75 - 100 | 爆满 | 建议错峰或外卖   |

---

## 六、项目文件结构

```
meal-index/
├── .github/
│   └── workflows/
│       └── update.yml   # GitHub Actions 定时任务工作流
├── pyproject.toml       # 项目依赖 (uv 管理)
├── passwd.env           # 账号密码 - 仅本地开发 (gitignored)
├── project.md           # 本文档
├── .gitignore           # 忽略 .env / .db / __pycache__ 等
├── vercel.json          # Vercel 静态部署配置（指向 web/ 目录）
├── config.py            # 配置常量（学期、校区、作息时间、阈值）
├── smu_login.py         # 自动登录模块（UIS + ddddocr）
├── fetcher.py           # 全校课表抓取（paginateQxkb 分页）
├── calculator.py        # 抢饭指数计算引擎（含自适应归一化）
├── database.py          # SQLite 持久化（建表 + 读写）
├── scheduler.py         # 定时任务入口（抓取 → 计算 → data.json）
├── web/
│   ├── index.html       # 静态前端页面（Vercel 部署）
│   └── data.json        # scheduler.py 运行时生成，git push 到仓库
└── meal_index.db        # SQLite 数据库（运行时生成，提交到仓库用于持久化）
```

---

## 七、数据库设计

### 表 1：meal_index（饭点抢饭指数 - 核心表）

```sql
CREATE TABLE IF NOT EXISTS meal_index (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,        -- '2026-03-09'
    campus      TEXT    NOT NULL,        -- '本部' / '顺德'
    meal_type   TEXT    NOT NULL,        -- '午饭' / '晚饭'
    score       REAL    NOT NULL,        -- 0-100 归一化分数
    level       TEXT    NOT NULL,        -- '畅通'/'一般'/'拥挤'/'爆满'
    head_count  INTEGER NOT NULL,        -- 饭点前下课总人数
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, campus, meal_type)
);
```

### 表 2：hourly_flow（逐节次人流明细）

```sql
CREATE TABLE IF NOT EXISTS hourly_flow (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,
    campus      TEXT    NOT NULL,
    end_node    INTEGER NOT NULL,        -- 下课节次号
    end_time    TEXT    NOT NULL,        -- 下课时间 '11:15'
    head_count  INTEGER NOT NULL,        -- 该节次下课人数
    UNIQUE(date, campus, end_node)
);
```

---

## 八、前端数据格式 (web/data.json)

`scheduler.py` 每次运行后生成 `web/data.json`，结构如下：

```json
{
  "date": "2026-03-09",
  "updated_at": "2026-03-09T07:05:30",
  "today": {
    "本部": {
      "午饭": { "score": 72.0, "level": "拥挤", "head_count": 1850, "end_time": "12:00" },
      "晚饭": { "score": 45.0, "level": "一般", "head_count": 1020, "end_time": "17:40" }
    },
    "顺德": {
      "午饭": { "score": 58.0, "level": "拥挤", "head_count": 1200, "end_time": "12:30" },
      "晚饭": { "score": 30.0, "level": "一般", "head_count": 680, "end_time": "17:10" }
    }
  },
  "hourly": {
    "本部": [
      { "end_node": 2, "end_time": "09:25", "head_count": 120 },
      { "end_node": 5, "end_time": "12:00", "head_count": 980 }
    ],
    "顺德": [ ... ]
  },
  "history": {
    "2026-03-08": {
      "本部": {
        "午饭": { "score": 65.0, "level": "拥挤", "head_count": 1600 },
        "晚饭": { "score": 40.0, "level": "一般", "head_count": 950 }
      },
      "顺德": { ... }
    }
  }
}
```

前端 `index.html` 通过 `fetch('./data.json')` 读取此文件并渲染。

---

## 九、数据流

```
[GitHub Actions cron UTC 23:00 = 北京 07:00]
    │
    ▼
scheduler.py
    ├─ smu_login.py      → 获取已认证的 requests.Session
    ├─ fetcher.py         → POST paginateQxkb（本部 + 顺德，自动分页）
    │                       过滤：排除 jxhjmc="自主学习"
    │                       过滤：本部只保留 jxcdmc 含"教室"，顺德含"春华堂"
    ├─ calculator.py      → 解析 jcdm 得到下课节次，按节次聚合 jxbrs
    │                       计算午饭/晚饭指数，自适应归一化 0-100
    ├─ database.py        → UPSERT 写入 meal_index + hourly_flow
    └─ 生成 web/data.json → 包含 today + hourly + history(7天)
    │
    ▼
[Actions commit & push]  → meal_index.db + web/data.json
    │
    ▼
[Vercel 静态托管]  ← 监听 push → 自动重新部署
    │
    ▼
web/index.html  ← fetch('./data.json') → 渲染抢饭指数
```

---

## 十、部署方式

### GitHub Actions 定时触发

- 工作流文件：`.github/workflows/update.yml`
- 触发方式：每天 UTC 23:00（北京时间 07:00）自动运行 + 支持手动触发 (`workflow_dispatch`)
- 流程：`uv sync` → `uv run python scheduler.py` → `git commit & push`（data.json + meal_index.db）
- 凭据：在仓库 Settings → Secrets → Actions 中设置 `ACCOUNT` 和 `PASSWORD`

**数据持久化**：`meal_index.db` 提交到仓库，每次 Actions 运行时 checkout 获取历史数据，运行后 commit 回去。这保证了自适应归一化所需的历史数据跨 run 可用。

### Vercel 静态托管

- 仓库 `vercel.json` 配置 `outputDirectory: "web"`
- Vercel 监听 GitHub 仓库的 push 事件，自动重新部署
- 前端 `index.html` 通过 `fetch('./data.json')` 读取数据
- `data.json` 设置 5 分钟缓存（`max-age=300`）

**无需自有服务器 / VPS / 常驻进程。**

---

## 十一、凭据配置

**GitHub Actions（生产）**：在仓库 Settings → Secrets and variables → Actions 中添加：

- `ACCOUNT`：学号
- `PASSWORD`：密码

**本地开发**：创建 `passwd.env` 文件（已 gitignore）：

```
ACCOUNT=学号
PASSWORD=密码
```

`smu_login.py` 优先读取环境变量，不存在时回退到 `passwd.env`。

---

## 十二、关键依赖

| 包                 | 用途                     |
| ------------------ | ------------------------ |
| `requests`       | HTTP 请求                |
| `beautifulsoup4` | HTML 解析（获取 xnxqdm） |
| `ddddocr==1.5.6` | OCR 验证码识别           |
| `Pillow`         | 验证码图片处理           |
| `python-dotenv`  | 环境变量加载             |

---

## 十三、注意事项

1. `passwd.env` 不应提交到 Git（已 gitignore）
2. `meal_index.db` 提交到仓库用于 GitHub Actions 历史数据持久化
3. `ddddocr` 的验证码识别有一定失败率，登录模块内置最多 5 次重试
4. 分页抓取时需要持续请求直到返回的 rows 为空或数量不足 rows 参数
5. `jcdm` 字段的解析：每 2 位一个节次号，取最后 2 位作为下课节次
6. 学期代码 `xnxqdm` 目前硬编码为 `202502`，换学期时需手动更新
