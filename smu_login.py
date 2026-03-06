"""
SMU Meal Index - 自动登录模块
基于 WakeUp4SMU 的 smulogin.py + auto_update.py 的 OCR 验证码逻辑。
"""

import time
import json
import logging
from hashlib import md5
from io import BytesIO

import requests
import ddddocr
from PIL import Image

from config import ENV_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UIS 统一认证地址
# ---------------------------------------------------------------------------
CAPTCHA_URL = "https://uis.smu.edu.cn/imageServlet.do"
LOGIN_URL = "https://uis.smu.edu.cn/login/login.do"
SSO_REDIRECT_URL = "https://zhjw.smu.edu.cn/new/ssoLogin"

# ---------------------------------------------------------------------------
# 请求 Headers
# ---------------------------------------------------------------------------
_CAPTCHA_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}

_LOGIN_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Host": "uis.smu.edu.cn",
    "Origin": "https://uis.smu.edu.cn",
    "Referer": "https://uis.smu.edu.cn/login.jsp?redirect="
    "https%3A%2F%2Fzhjw.smu.edu.cn%2Fnew%2FssoLogin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "X-KL-kis-Ajax-Request": "Ajax_Request",
    "X-Requested-With": "XMLHttpRequest",
}

_SSO_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Host": "zhjw.smu.edu.cn",
    "Referer": "https://zhjw.smu.edu.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}

# ---------------------------------------------------------------------------
# OCR 实例（全局复用）
# ---------------------------------------------------------------------------
_ocr: ddddocr.DdddOcr | None = None


def _get_ocr() -> ddddocr.DdddOcr:
    """懒加载 OCR 实例。"""
    global _ocr
    if _ocr is None:
        _ocr = ddddocr.DdddOcr(beta=True)
    return _ocr


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------


def _fetch_and_solve_captcha(session: requests.Session) -> str:
    """获取验证码图片并用 OCR 识别。"""
    resp = session.get(CAPTCHA_URL, headers=_CAPTCHA_HEADERS)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content))
    result = _get_ocr().classification(img)
    logger.debug("验证码识别结果: %s", result)
    return result


def _send_login(
    account: str, password: str, captcha: str, session: requests.Session
) -> str | None:
    """向 UIS 发送登录请求，成功返回 ticket，失败返回 None。"""
    password_md5 = md5(password.encode()).hexdigest()
    data = {
        "loginName": account,
        "password": password_md5,
        "randcodekey": captcha,
        "locationBrowser": "谷歌浏览器[Chrome]",
        "appid": "3550176",
        "redirect": SSO_REDIRECT_URL,
        "strength": 3,
    }
    resp = session.post(LOGIN_URL, data=data, headers=_LOGIN_HEADERS)
    if resp.status_code == 200 and "成功" in resp.text:
        resp_json = json.loads(resp.text)
        ticket = resp_json.get("ticket")
        logger.info("UIS 登录成功，获取 ticket")
        return ticket
    logger.warning("UIS 登录失败: %s", resp.text)
    return None


def _sso_redirect(session: requests.Session, ticket: str) -> None:
    """使用 ticket 完成教务系统 SSO 跳转。"""
    resp = session.get(
        SSO_REDIRECT_URL, headers=_SSO_HEADERS, params={"ticket": ticket}
    )
    logger.info("SSO 跳转状态码: %d", resp.status_code)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def load_credentials() -> tuple[str, str]:
    """
    加载账号密码。

    优先从环境变量 ACCOUNT / PASSWORD 读取（适用于 GitHub Actions），
    若不存在则从 passwd.env 文件读取（本地开发）。
    """
    import os

    account = os.environ.get("ACCOUNT", "")
    password = os.environ.get("PASSWORD", "")

    if account and password:
        logger.info("从环境变量加载凭据")
        return account, password

    # 回退: 从 passwd.env 文件读取
    if ENV_PATH.exists():
        creds: dict[str, str] = {}
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    creds[key.strip()] = value.strip()
        account = creds.get("ACCOUNT", "")
        password = creds.get("PASSWORD", "")
        if account and password:
            logger.info("从 passwd.env 加载凭据")
            return account, password

    raise ValueError(
        f"未找到凭据。请设置环境变量 ACCOUNT/PASSWORD，或创建 {ENV_PATH} 文件。"
    )


def login(
    session: requests.Session | None = None, max_retries: int = 5
) -> requests.Session:
    """
    自动登录教务系统，返回已认证的 Session。

    Parameters
    ----------
    session : requests.Session, optional
        如果为 None 则创建新 Session。
    max_retries : int
        验证码识别/登录失败时的最大重试次数。

    Returns
    -------
    requests.Session
        已完成 SSO 认证、可直接请求教务系统接口的 Session。

    Raises
    ------
    RuntimeError
        超过重试次数仍无法登录时抛出。
    """
    if session is None:
        session = requests.Session()

    account, password = load_credentials()

    for attempt in range(1, max_retries + 1):
        logger.info("登录尝试 %d/%d ...", attempt, max_retries)
        try:
            captcha = _fetch_and_solve_captcha(session)
            ticket = _send_login(account, password, captcha, session)
            if ticket:
                _sso_redirect(session, ticket)
                logger.info("教务系统登录完成")
                return session
        except Exception as e:
            logger.warning("登录尝试 %d 异常: %s", attempt, e)

        logger.info("登录失败（可能验证码识别错误），等待重试...")
        time.sleep(1)

    raise RuntimeError(f"登录失败，已重试 {max_retries} 次")
