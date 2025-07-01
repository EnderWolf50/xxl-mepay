import asyncio
import re
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from xxl_mepay.models import CollectedResult

_SUPPORT_CODE_PATTERN = re.compile(
    r"https://www\.mepay\.com\.tw/XXL\?supportCode=([a-zA-Z0-9=]+)"
)


def extract_support_codes(text: str) -> set[str]:
    return set(_SUPPORT_CODE_PATTERN.findall(text))


def extract_support_codes_in_page(soup: BeautifulSoup) -> set[str]:
    extracted_codes: set[str] = set()

    contents = soup.select(".c-post__body .c-article .c-article__content")
    for content in contents:
        content_text = content.get_text()
        extracted_codes.update(extract_support_codes(content_text))

    return extracted_codes


def parse_page_number_from_url(url: str) -> int:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    page_param = query_params.get("page")
    if page_param is None:
        raise ValueError("Page parameter not found in URL")
    try:
        return int(page_param[0])
    except ValueError:
        raise ValueError("Page parameter is not a valid integer")


def get_max_page_number(soup: BeautifulSoup) -> int:
    page_numbers = []
    pagination = soup.select_one("p.BH-pagebtnA")
    if pagination is None:
        return 1

    pages = pagination.select("a")
    for page in pages:
        page_class = page.get("class")
        if isinstance(page_class, list) and "pagenow" in page_class:
            page_numbers.append(int(page.get_text()))
            continue

        href = page.get("href")
        if not isinstance(href, str) or "?page=" not in href:
            continue
        try:
            page_number = parse_page_number_from_url(href)
            page_numbers.append(page_number)
        except ValueError:
            continue

    return max(page_numbers) if page_numbers else 1


async def collect_first_floor_comment_support_codes(
    client: httpx.AsyncClient,
) -> set[str]:
    res = await client.get(
        "https://forum.gamer.com.tw/ajax/moreCommend.php",
        params={"bsn": "80107", "snB": "161"},
    )
    if res.status_code != 200:
        return set()

    data: dict[str, dict[str, str | int] | int] = res.json()

    comments = set()
    for value in data.values():
        if isinstance(value, int):
            continue

        comment = value.get("comment")
        if comment is None or not isinstance(comment, str):
            continue
        comments.update(extract_support_codes(comment))

    return comments


async def collect_max_page_and_support_codes(
    start_page: int = 1,
) -> CollectedResult:
    codes: set[str] = set()
    base_url = "https://forum.gamer.com.tw/C.php"
    base_params = {"bsn": "80107", "snA": "67"}

    async with httpx.AsyncClient() as client:
        first_page_res = await client.get(
            base_url, params={**base_params, "page": start_page}
        )
        first_page_soup = BeautifulSoup(first_page_res.text, "html.parser")

        first_page_codes = extract_support_codes_in_page(first_page_soup)
        codes.update(first_page_codes)

        first_floor_comment_codes = await collect_first_floor_comment_support_codes(
            client
        )
        codes.update(first_floor_comment_codes)

        max_page = get_max_page_number(first_page_soup)

        tasks = [
            client.get(base_url, params={**base_params, "page": page_num})
            for page_num in range(max(2, start_page), max_page + 1)
        ]
        if not tasks:
            return CollectedResult(max_page, codes)

        page_responses: list[httpx.Response] = await asyncio.gather(*tasks)
        for page_res in page_responses:
            page_soup = BeautifulSoup(page_res.text, "html.parser")
            page_codes = extract_support_codes_in_page(page_soup)
            codes.update(page_codes)

    return CollectedResult(max_page, codes)
