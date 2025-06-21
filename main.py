import json
import sys
import time
from urllib.parse import parse_qs, unquote, urlparse

import bs4
import requests
from playwright.sync_api import TimeoutError, expect, sync_playwright

# --- Configuration for Progress File ---
PROGRESS_FILE = "progress.json"


# --- Functions for Progress File Management ---
def load_progress(filename: str = PROGRESS_FILE) -> dict:
    """Loads progress data from a JSON file."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure processed_urls is a set for efficient lookups
            if "processed_urls" in data and isinstance(data["processed_urls"], list):
                data["processed_urls"] = set(data["processed_urls"])
            else:
                data["processed_urls"] = set()
            return data
    except FileNotFoundError:
        print(f"Progress file '{filename}' not found. Starting with empty progress.")
    except json.JSONDecodeError:
        print(f"Error decoding JSON from '{filename}'. Starting with empty progress.")
    return {"last_max_page": 1, "processed_urls": set()}


def save_progress(data: dict, filename: str = PROGRESS_FILE):
    """Saves progress data to a JSON file."""
    # Convert set back to list for JSON serialization
    if "processed_urls" in data and isinstance(data["processed_urls"], set):
        copy = data.copy()
        copy["processed_urls"] = sorted(list(copy["processed_urls"]))
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(copy, f, indent=4, ensure_ascii=False)
        # print(f"Progress saved to '{filename}'.") # Optional: remove for less verbosity
    except IOError as e:
        print(f"Error saving progress to '{filename}': {e}")


# --- Prompt the user for username (email) and password ---
EMAIL = input("Please enter your MePay email: ")
PASSWORD = input("Please enter your MePay password: ")


# --- Optimized Page and Link Fetching ---
def get_mepay_links_from_soup(soup_obj: bs4.BeautifulSoup) -> list[str]:
    """
    Extracts MePay XXL links from a BeautifulSoup object.
    These are links like 'www.mepay.com.tw/XXL' embedded in a redir.
    """
    extracted_links = []
    a_tags = soup_obj.find_all("a")
    for a in a_tags:
        if isinstance(a, bs4.element.Tag):
            href = a.get("href")
            if isinstance(href, str) and "www.mepay.com.tw%2FXXL" in href:
                cleaned_link = unquote(
                    href.replace("https://ref.gamer.com.tw/redir.php?url=", "")
                )
                extracted_links.append(cleaned_link)
    return extracted_links


def get_max_page_number(soup_obj: bs4.BeautifulSoup) -> int:
    """
    Parses the pagination div to find the maximum page number.
    Returns 1 if no pagination links are found.
    """
    page_numbers = []
    pagination_div = soup_obj.find("p", class_="BH-pagebtnA")

    if isinstance(pagination_div, bs4.element.Tag):
        for a_tag in pagination_div.find_all("a"):
            if isinstance(a_tag, bs4.element.Tag):
                href = a_tag.get("href")
                if isinstance(href, str) and "?page=" in href:
                    parsed_href = urlparse(href)
                    query_params = parse_qs(parsed_href.query)
                    page_param = query_params.get("page")
                    if page_param and page_param[0].isdigit():
                        try:
                            page_numbers.append(int(page_param[0]))
                        except ValueError:
                            continue
    return max(page_numbers) if page_numbers else 1


# --- Main Script Execution ---

# 0. Load existing progress
progress_data = load_progress()
last_max_page_recorded = progress_data["last_max_page"]
processed_urls = progress_data["processed_urls"]  # This is a set

print(f"Previously recorded max page: {last_max_page_recorded}")
print(f"Number of previously processed URLs: {len(processed_urls)}")

links = []
base_forum_url = (
    "https://forum.gamer.com.tw/C.php?bsn=80107&snA=67&subbsn=0&threadSubbsn=8"
)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"
}

# 1. Fetch the first page to determine max_page and get its links
print("Fetching initial page to determine total pages and links...")
try:
    res = requests.get(f"{base_forum_url}&page=1", headers=headers, timeout=15)
    res.raise_for_status()
    initial_soup = bs4.BeautifulSoup(res.text, "html.parser")

    current_max_page = get_max_page_number(initial_soup)
    # Always get links from page 1, as it's the anchor point and might change
    links.extend(get_mepay_links_from_soup(initial_soup))
    print(f"Determined a total of {current_max_page} pages.")

except requests.exceptions.RequestException as e:
    print(f"Error fetching initial page: {e}")
    print(
        "Cannot proceed with link scraping. Please check your internet connection or the URL."
    )
    sys.exit(1)

# 2. Loop through remaining pages and collect links
start_fetching_page = max(2, last_max_page_recorded)

if start_fetching_page > current_max_page:
    print(
        f"No new pages to fetch (max page {current_max_page} <= previously recorded {last_max_page_recorded})."
    )
else:
    for page_num in range(start_fetching_page, current_max_page + 1):
        page_url = f"{base_forum_url}&page={page_num}"
        print(f"Fetching links from page {page_num}/{current_max_page}...")
        try:
            res = requests.get(page_url, headers=headers, timeout=15)
            res.raise_for_status()
            soup = bs4.BeautifulSoup(res.text, "html.parser")
            links.extend(get_mepay_links_from_soup(soup))
            time.sleep(1)  # Be polite: 1 second delay between requests
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page_num}: {e}. Skipping this page.")
            continue


# 3. Remove duplicates from the newly scraped links (within this run)
original_link_count = len(links)
links = list(dict.fromkeys(links))

if original_link_count != len(links):
    print(
        f"Removed {original_link_count - len(links)} duplicate links found in this scraping session."
    )
print(f"Found a total of {len(links)} unique MePay links across all pages.")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context()

    # --- Speed Up: Block unnecessary resources ---
    # Abort requests for images, fonts, and video/audio
    context.route(
        "**/*.{png,jpg,jpeg,gif,webp,svg,mp4,webm,ogg,mp3,wav,ttf,woff,woff2}",
        lambda route: route.abort(),
    )
    # You could also block specific domains if they are known ad/tracker networks, e.g.:
    # context.route("**/google-analytics.com/**", lambda route: route.abort())
    # context.route("**/doubleclick.net/**", lambda route: route.abort())
    # Be careful blocking CSS/JS, as it might break page functionality needed for interaction.

    page = context.new_page()

    page.goto("https://www.mepay.com.tw/XXL", timeout=30000)

    try:
        announcement = page.locator("text=通知公告")
        if announcement.locator(".dialog-close").is_visible():
            announcement.locator(".dialog-close").click()
    except Exception as e:
        print(f"Could not find or close notification dialog: {e}")

    page.click(".login-btn")

    page.wait_for_timeout(2000)
    page.fill('input[name="email"]', EMAIL)
    page.fill('input[name="password"]', PASSWORD)

    page.click(".modal button:has-text('登入')")

    try:
        expect(page.locator("text=登出")).to_be_visible(timeout=15000)
        print("Successfully logged in.")
    except TimeoutError:
        print("Login failed or took too long. Check your credentials.")
        browser.close()
        sys.exit(1)

    # 8) now iterate your links
    processed_count = 0
    skipped_count = 0
    error_count = 0

    for i, url in enumerate(links):
        if url in processed_urls:  # Check if URL was processed in a previous run
            print(
                f"[{i + 1}/{len(links)}] [SKIP] Already processed in a previous run: {url}"
            )
            skipped_count += 1
            continue  # Skip to the next URL

        print(f"\n[{i + 1}/{len(links)}] Processing link: {url}")
        try:
            # --- Speed Up: Removed page.wait_for_load_state("networkidle") here ---
            # Rely on the 'expect' statements to signal page readiness.
            page.goto(url, timeout=30000)

            support_btn = page.get_by_role("button", name="我來應援你!")
            back_btn = page.get_by_role("button", name="返回")

            expect(support_btn.or_(back_btn)).to_be_visible(timeout=10_000)

            if support_btn.is_visible():
                print(f"[ACTION] Clicking '我來應援你!' on {url}")
                support_btn.click()

                success_msg_locator = page.locator(".share-support-success-modal")
                # Increased timeout for success message as it might be an overlay
                expect(success_msg_locator).to_be_visible(timeout=15_000)
                print(f"[SUCCESS] Support confirmed for {url}")
                progress_data["processed_urls"].add(
                    url
                )  # Add to the set of processed URLs
                processed_count += 1

            elif back_btn.is_visible():
                print(f"[SKIP] Already supported (found '返回' button) on {url}")
                progress_data["processed_urls"].add(
                    url
                )  # Also mark as processed if '返回' is found
                skipped_count += 1
            # --- Update JSON after skipping (due to '返回' button) ---
            save_progress(progress_data)

        except TimeoutError as e:
            print(
                f"[TIMEOUT] on {url}. Neither button appeared or an expected element took too long. Error: {e}"
            )
            error_count += 1
            # You might or might not want to save progress on timeout/error.
            # For now, it's not saved to retry next time.
            continue

    browser.close()
    print("\n--- Script Summary ---")
    print(f"Total unique links found: {len(links)}")
    print(f"Links processed this run: {processed_count}")
    print(f"Links skipped (already supported/processed): {skipped_count}")
    print(f"Links with errors/timeouts: {error_count}")
    print("Script finished. Browser closed.")

# 9. Final Save of updated progress (redundant if saved per-iteration, but good as a fallback)
progress_data["last_max_page"] = current_max_page
save_progress(progress_data)
