import asyncio
import re
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from xxl_mepay.models import CollectedResult, ExtractedResult

_SUPPORT_CODE_PATTERN = re.compile(
    r"https://www\.mepay\.com\.tw/XXL\?supportCode=([a-zA-Z0-9=]+)"
)
_REURL_PATTERN = re.compile(r"https://reurl.cc/[0-9a-zA-Z]+")


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


def extract_support_codes(text: str) -> set[str]:
    return set(_SUPPORT_CODE_PATTERN.findall(text))


def extract_reurls(text: str) -> set[str]:
    return set(_REURL_PATTERN.findall(text))


async def parse_first_floor_comments(
    client: httpx.AsyncClient,
) -> ExtractedResult:
    res = await client.get(
        "https://forum.gamer.com.tw/ajax/moreCommend.php",
        params={"bsn": "80107", "snB": "161"},
    )
    if res.status_code != 200:
        return ExtractedResult()

    data: dict[str, dict[str, str | int] | int] = res.json()

    codes = set()
    reurls = set()
    for value in data.values():
        if isinstance(value, int):
            continue

        comment = value.get("comment")
        if comment is None or not isinstance(comment, str):
            continue
        codes.update(extract_support_codes(comment))
        reurls.update(extract_reurls(comment))

    return ExtractedResult(support_codes=codes, reurl_links=reurls)


def parse_page(soup: BeautifulSoup) -> ExtractedResult:
    extracted_codes: set[str] = set()
    extracted_reurls: set[str] = set()

    contents = soup.select(".c-post__body .c-article .c-article__content")
    for content in contents:
        content_text = content.get_text()
        extracted_codes.update(extract_support_codes(content_text))
        extracted_reurls.update(extract_reurls(content_text))

    return ExtractedResult(support_codes=extracted_codes, reurl_links=extracted_reurls)


async def collect_forum_data(
    start_page: int = 1,
) -> CollectedResult:
    base_url = "https://forum.gamer.com.tw/C.php"
    base_params = {"bsn": "80107", "snA": "67"}

    codes: set[str] = set()
    reurls: set[str] = set()

    async with httpx.AsyncClient() as client:
        first_page_res = await client.get(
            base_url, params={**base_params, "page": start_page}
        )
        first_page_soup = BeautifulSoup(first_page_res.text, "html.parser")

        first_page_result = parse_page(first_page_soup)
        codes.update(first_page_result.support_codes)
        reurls.update(first_page_result.reurl_links)

        first_floor_comment_result = await parse_first_floor_comments(client)
        codes.update(first_floor_comment_result.support_codes)
        reurls.update(first_floor_comment_result.reurl_links)

        max_page = get_max_page_number(first_page_soup)

        tasks = [
            client.get(base_url, params={**base_params, "page": page_num})
            for page_num in range(max(2, start_page), max_page + 1)
        ]
        if not tasks:
            return CollectedResult(max_page, codes, reurls)

        page_responses: list[httpx.Response] = await asyncio.gather(*tasks)
        for page_res in page_responses:
            page_soup = BeautifulSoup(page_res.text, "html.parser")
            page_result = parse_page(page_soup)
            codes.update(page_result.support_codes)
            reurls.update(page_result.reurl_links)

    return CollectedResult(max_page, codes, reurls)
