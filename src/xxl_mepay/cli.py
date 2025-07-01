import asyncio

import inquirer

from xxl_mepay.auth import login
from xxl_mepay.bahamut import collect_max_page_and_support_codes
from xxl_mepay.mepay import support_user
from xxl_mepay.state import (
    get_previous_password,
    load_progress,
    save_password,
    save_progress,
)
from xxl_mepay.utils import error, info, result, skip, tip


async def _run() -> None:
    progress = load_progress()

    previous_email = progress.get("email")
    email: str = inquirer.text("請輸入你的魔儲信箱", default=previous_email)
    previous_password = get_previous_password(email)
    password: str = inquirer.password("請輸入你的魔儲密碼", default=previous_password)

    if not email.strip():
        raise ValueError("信箱不能為空")
    if not password.strip():
        raise ValueError("密碼不能為空")

    tip("可以使用 Ctrl + C 停止運行（沒用的話可以多點幾次）")

    last_max_page = progress.get("last_max_page")
    processed_codes = progress.get("processed_codes", set())

    if previous_email != email or previous_password != password:
        remember: bool = inquirer.confirm("要記住這個信箱和密碼嗎？")
        if remember:
            save_progress({**progress, "email": email})
            save_password(email, password)

    info("正在登入魔儲...")
    mepay_token = await login(email, password)

    info("抓取最新應援碼...")
    collected_result = await collect_max_page_and_support_codes(
        last_max_page if last_max_page is not None else 1
    )

    info(f"先前最後抓取頁數: {last_max_page}")
    info(f"先前已處理應援碼數: {len(processed_codes)}")
    info(f"本次抓取頁數: {collected_result.max_page}")
    info(f"本次抓取應援碼數: {len(collected_result.support_codes)}")

    for support_code in collected_result.support_codes:
        if support_code in processed_codes:
            skip(f"已有應援紀錄，跳過: {support_code}")
            continue

        support_result = support_user(mepay_token, support_code)

        processed_codes |= {support_code}
        save_progress(
            {
                "email": email,
                "last_max_page": last_max_page,
                "processed_codes": processed_codes,
            }
        )

        result(support_result["message"])

    save_progress(
        {
            "email": email,
            "last_max_page": collected_result.max_page,
            "processed_codes": processed_codes,
        }
    )


def main():
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        error("已停止運行")
    except Exception as e:
        error(f"發生錯誤: {e}")
    finally:
        input("按 Enter 鍵以關閉程式...")
