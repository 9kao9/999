"""ทดลองดึงผลหวย 9 หน้าผ่าน ScrapingAnt โดยไม่ต้องเปิดคอมพิวเตอร์

API key ต้องเก็บใน GitHub Secret ชื่อ SCRAPINGANT_API_KEY เท่านั้น
ห้ามเขียน API key ลงในไฟล์นี้
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


PAGES = {
    "government": "https://news.sanook.com/lotto/",
    "lao": "https://laodl.com/api/website/laolot/WinPrizeHistory?type=1",
    "hanoi_special": "https://www.xsthm.com/result",
    "hanoi_normal": "https://www.minhngoc.net.vn/ket-qua-xo-so/mien-bac.html",
    "hanoi_vip": "https://www.mlnhngoc.net/mlnhngoc",
    "dow": "https://www.msn.com/en-us/money/indexdetails/fi-a6qja2",
    "nikkei_morning": "https://indexes.nikkei.co.jp/en/nkave",
    "nikkei_afternoon": "https://indexes.nikkei.co.jp/en/nkave",
    "thai_stock": "https://www.set.or.th/th/market/index/set/overview",
}

SET50_URL = "https://www.set.or.th/th/market/index/set50/overview"

DATA_FILE = Path(__file__).with_name("results.json")
THAI_TZ = timezone(timedelta(hours=7), name="Asia/Bangkok")
MAX_HISTORY_PER_TYPE = 730
SCRAPINGANT_ENDPOINT = "https://api.scrapingant.com/v2/general"
THAI_MONTHS = {
    "มกราคม": 1,
    "กุมภาพันธ์": 2,
    "มีนาคม": 3,
    "เมษายน": 4,
    "พฤษภาคม": 5,
    "มิถุนายน": 6,
    "กรกฎาคม": 7,
    "สิงหาคม": 8,
    "กันยายน": 9,
    "ตุลาคม": 10,
    "พฤศจิกายน": 11,
    "ธันวาคม": 12,
}
RESULT_SELECTORS = (
    "div.bg-gray-200.text-xl.text-black.font-semibold",
    "[data-result]",
    "[class*='result'] [class*='number']",
    "main [class*='font-semibold']",
)


def empty_data() -> dict:
    return {**{key: [] for key in PAGES}, "_meta": {}}


def load_data() -> dict:
    if not DATA_FILE.exists():
        return empty_data()
    with DATA_FILE.open(encoding="utf-8") as file:
        data = json.load(file)
    for key in PAGES:
        if not isinstance(data.get(key), list):
            data[key] = []
    if not isinstance(data.get("_meta"), dict):
        data["_meta"] = {}
    return data


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def fetch_html(
    api_key: str,
    target_url: str,
    render_javascript: bool,
) -> str:
    # A fragment makes ScrapingAnt see a unique URL, while browsers do not send
    # the fragment to ExpHuay. This avoids stale provider cache without making
    # ExpHuay see an unfamiliar query string that can trigger bot protection.
    cache_busted_url = (
        f"{target_url}#_scrape_ts="
        f"{int(datetime.now(timezone.utc).timestamp())}"
    )
    # Try the inexpensive request first. If ExpHuay requires rendering, use
    # JavaScript only once. A successful Cloudflare challenge page is charged
    # like a normal browser request, so repeating it would waste credits.
    attempts = [(target_url, False, "lightweight attempt")]
    if render_javascript:
        attempts.append((cache_busted_url, True, "JavaScript attempt"))
    last_html = ""

    for attempt_number, (attempt_url, use_browser, label) in enumerate(
        attempts,
        start=1,
    ):
        response = requests.get(
            SCRAPINGANT_ENDPOINT,
            params={
                "x-api-key": api_key,
                "url": attempt_url,
                "browser": "true" if use_browser else "false",
                "proxy_type": "datacenter",
                "timeout": "60",
            },
            timeout=90,
        )
        credit_cost = response.headers.get("Ant-credits-cost")
        credit_note = f", credits={credit_cost}" if credit_cost else ""
        if not response.ok:
            detail = response.text.strip().replace("\n", " ")[:500]
            if response.status_code == 423 and attempt_number < len(attempts):
                next_label = attempts[attempt_number][2]
                print(
                    f"ScrapingAnt blocked {label} with HTTP 423{credit_note}; "
                    f"retrying with {next_label}...",
                    file=sys.stderr,
                )
                continue
            raise RuntimeError(
                f"ScrapingAnt HTTP {response.status_code}: {detail}"
            )

        last_html = response.text
        print(
            f"ScrapingAnt succeeded with {label}{credit_note}",
            file=sys.stderr,
        )
        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            last_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        title = (
            BeautifulSoup(title_match.group(1), "html.parser").get_text(
                " ",
                strip=True,
            )
            if title_match
            else ""
        )
        if title.lower() not in {"just a moment...", "รอสักครู่..."}:
            return last_html

        print(
            "พบหน้าป้องกันบอต กำลังลองใหม่ด้วย URL ปกติ...",
            file=sys.stderr,
        )

    return last_html


def fetch_direct_html(target_url: str) -> str:
    """Fetch a static result page without spending ScrapingAnt credits."""
    response = requests.get(
        target_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0 Safari/537.36"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        },
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def fetch_direct_json(target_url: str) -> dict:
    """Fetch a public JSON result endpoint without ScrapingAnt."""
    response = requests.get(
        target_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0 Safari/537.36"
            ),
            "Accept": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("result endpoint returned invalid JSON")
    return payload


def parse_msn_dow(html: str) -> tuple[str, str, str, str]:
    """Read the closed Dow value and change from MSN Money.

    Lottery conversion:
    - top 3 = last digit of the five-digit index + its two decimals
    - bottom 2 = two decimals of the signed change shown after ``at close``
    - main = top 3 followed by bottom 2
    """
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    page_text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", page_text)
    page_text = re.sub(r"\s+", " ", page_text)

    if "DOW (DJI)" not in page_text:
        raise RuntimeError("MSN: ไม่พบหัวข้อ DOW (DJI)")

    match = re.search(
        r"(?P<index>\d{1,3}(?:,\d{3})+\.\d{2})\s+"
        r"at close\s+"
        r"(?P<change>[+\-−]\s*\d[\d,]*\.\d{2})"
        r".{0,160}?as of\s+"
        r"(?P<date>\d{1,2}/\d{1,2}/\d{4})",
        page_text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise RuntimeError("MSN: ไม่พบดัชนี ค่า at close หรือวันที่ as of ครบชุด")

    index_value = match.group("index")
    index_integer, index_decimals = index_value.replace(",", "").split(".")
    if len(index_integer) != 5 or len(index_decimals) != 2:
        raise RuntimeError(f"MSN: รูปแบบดัชนีไม่ใช่เลข 5 หลักและทศนิยม 2 หลัก: {index_value}")

    change_value = match.group("change").replace(" ", "").replace("−", "-")
    change_decimals = change_value.rsplit(".", 1)[-1]
    if len(change_decimals) != 2:
        raise RuntimeError(f"MSN: รูปแบบค่าเปลี่ยนแปลงไม่ถูกต้อง: {change_value}")

    try:
        draw_date = datetime.strptime(match.group("date"), "%m/%d/%Y").date()
    except ValueError as exc:
        raise RuntimeError(f"MSN: วันที่ as of ไม่ถูกต้อง: {match.group('date')}") from exc

    top3 = index_integer[-1] + index_decimals
    bottom2 = change_decimals
    main_number = top3 + bottom2
    return draw_date.isoformat(), main_number, top3, bottom2


def parse_nikkei_225(html: str) -> tuple[str, str, str, str]:
    """Read the main Nikkei 225 value and its change from the official site.

    Lottery conversion:
    - top 3 = last digit of the index integer + its two decimals
    - bottom 2 = two decimals of the signed index change
    - main = top 3 followed by bottom 2
    """
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    page_text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", page_text)
    page_text = re.sub(r"\s+", " ", page_text)

    match = re.search(
        r"Nikkei\s+225\s+"
        r"(?P<date>[A-Za-z]{3}/\d{1,2}/\d{4})"
        r"\s*(?:\([^)]*\))?\s+"
        r"(?P<index>\d{1,3}(?:,\d{3})+\.\d{2})\s+"
        r"(?P<change>[+\-−]\s*\d[\d,]*\.\d{2})\s+"
        r"[+\-−]\s*\d[\d,]*\.\d+%",
        page_text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise RuntimeError(
            "Nikkei: ไม่พบวันที่ ค่าดัชนีหลัก และค่าเปลี่ยนแปลงในหัวข้อ Nikkei 225"
        )

    index_value = match.group("index")
    index_integer, index_decimals = index_value.replace(",", "").split(".")
    if len(index_integer) != 5 or len(index_decimals) != 2:
        raise RuntimeError(
            f"Nikkei: รูปแบบดัชนีไม่ใช่เลข 5 หลักและทศนิยม 2 หลัก: {index_value}"
        )

    change_value = match.group("change").replace(" ", "").replace("−", "-")
    change_decimals = change_value.rsplit(".", 1)[-1]
    if len(change_decimals) != 2:
        raise RuntimeError(
            f"Nikkei: รูปแบบค่าเปลี่ยนแปลงไม่ถูกต้อง: {change_value}"
        )

    try:
        draw_date = datetime.strptime(match.group("date"), "%b/%d/%Y").date()
    except ValueError as exc:
        raise RuntimeError(
            f"Nikkei: วันที่กำกับดัชนีไม่ถูกต้อง: {match.group('date')}"
        ) from exc

    top3 = index_integer[-1] + index_decimals
    bottom2 = change_decimals
    main_number = top3 + bottom2
    return draw_date.isoformat(), main_number, top3, bottom2


def parse_set_thai_stock(
    set50_html: str,
    set_html: str,
) -> tuple[str, str, str, str]:
    """Build the Thai evening stock result from official SET50 and SET data."""

    def clean_text(html: str) -> str:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", text)
        return re.sub(r"\s+", " ", text)

    set50_text = clean_text(set50_html)
    set_text = clean_text(set_html)
    number_pattern = r"\d{1,3}(?:,\d{3})*\.\d{2}"
    change_pattern = r"[+\-−]\s*\d[\d,]*\.\d{2}"

    set50_match = re.search(
        rf"ดัชนีราคา\s+SET50.*?\bSET50\b\s+ดัชนี\s+"
        rf"(?P<index>{number_pattern})\s+"
        rf"(?P<change>{change_pattern})",
        set50_text,
        flags=re.IGNORECASE,
    )
    set_match = re.search(
        rf"ดัชนีราคาหุ้นตลาดหลักทรัพย์แห่งประเทศไทย.*?\bSET\b\s+ดัชนี\s+"
        rf"(?P<index>{number_pattern})\s+"
        rf"(?P<change>{change_pattern})",
        set_text,
        flags=re.IGNORECASE,
    )
    if not set50_match:
        raise RuntimeError("SET50: ไม่พบค่าดัชนีหลักและค่าความเปลี่ยนแปลง")
    if not set_match:
        raise RuntimeError("SET: ไม่พบค่าดัชนีหลักและค่าความเปลี่ยนแปลง")

    # SET currently reports a finished trading session as either "Closed" or
    # "OffHour".  Treat both as final; other states may still contain intraday
    # values and must not be saved as the evening result.
    final_market_status = r"สถานะตลาด\s*:\s*(?:Closed|OffHour)\b"
    if not re.search(final_market_status, set50_text, re.IGNORECASE):
        raise RuntimeError("SET50: ตลาดยังไม่แสดงสถานะ Closed หรือ OffHour")
    if not re.search(final_market_status, set_text, re.IGNORECASE):
        raise RuntimeError("SET: ตลาดยังไม่แสดงสถานะ Closed หรือ OffHour")

    thai_short_months = {
        "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4,
        "พ.ค.": 5, "มิ.ย.": 6, "ก.ค.": 7, "ส.ค.": 8,
        "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
    }

    def extract_date(text: str, label: str) -> str:
        match = re.search(
            r"ข้อมูลล่าสุด\s*:?[ ]*(\d{1,2})\s+([ก-๙.]+)\s+(\d{4})",
            text,
        )
        if not match or match.group(2) not in thai_short_months:
            raise RuntimeError(f"{label}: ไม่พบวันที่ข้อมูลล่าสุด")
        day, month_name, year = match.groups()
        christian_year = int(year) - 543 if int(year) > 2400 else int(year)
        return datetime(
            christian_year,
            thai_short_months[month_name],
            int(day),
        ).date().isoformat()

    set50_date = extract_date(set50_text, "SET50")
    set_date = extract_date(set_text, "SET")
    if set50_date != set_date:
        raise RuntimeError(
            f"SET: วันที่ SET50 ({set50_date}) และ SET ({set_date}) ไม่ตรงกัน"
        )

    set50_decimals = set50_match.group("index").rsplit(".", 1)[-1]
    set_decimals = set_match.group("index").rsplit(".", 1)[-1]
    change_decimals = (
        set_match.group("change").replace(" ", "").replace("−", "-")
        .rsplit(".", 1)[-1]
    )
    top3 = set50_decimals[-1] + set_decimals
    bottom2 = change_decimals
    main_number = top3 + bottom2
    return set_date, main_number, top3, bottom2


def parse_sanook_government(html: str) -> tuple[str, str, str, str]:
    """Read only Sanook's current government-lottery section, not history."""
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    page_text = re.sub(r"\s+", " ", page_text)

    months = {
        "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3,
        "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6,
        "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9,
        "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
    }
    match = re.search(
        r"ตรวจสลากกินแบ่งรัฐบาล\s+ตรวจหวย\s+"
        r"(?P<day>\d{1,2})\s+"
        r"(?P<month>[ก-๙]+)\s+"
        r"(?P<year>\d{4})\s+"
        r"(?P<main>\d{6})\s+รางวัลที่\s*1\b"
        r".{0,500}?"
        r"(?P<bottom>\d{2})\s+เลขท้าย\s*2\s*ตัว\b",
        page_text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise RuntimeError(
            "Sanook: ไม่พบงวดล่าสุดครบชุดใต้หัวข้อ ตรวจสลากกินแบ่งรัฐบาล"
        )

    month_name = match.group("month")
    if month_name not in months:
        raise RuntimeError(f"Sanook: ไม่รู้จักชื่อเดือน {month_name!r}")
    year = int(match.group("year"))
    christian_year = year - 543 if year > 2400 else year
    draw_date = datetime(
        christian_year,
        months[month_name],
        int(match.group("day")),
    ).date().isoformat()

    main_number = match.group("main")
    top3 = main_number[-3:]
    bottom2 = match.group("bottom")
    return draw_date, main_number, top3, bottom2


def parse_xsthm_special(payload: dict) -> tuple[str, str, str, str]:
    """Read Hanoi special from xsthm.com's public real-time endpoint."""
    items = payload.get("items")
    label = str(payload.get("label", "")).strip()
    if not isinstance(items, list) or len(items) < 2:
        raise RuntimeError("xsthm.com: latest draw is incomplete")

    first_prize = digits_only(str(items[0]))
    main_number = digits_only(str(items[-1]))
    if len(main_number) != 5 or len(first_prize) != 5:
        raise RuntimeError(
            "xsthm.com: special or first prize is not complete"
        )
    try:
        draw_date = datetime.strptime(label, "%d-%m-%Y").date()
    except ValueError as exc:
        raise RuntimeError(f"xsthm.com: invalid draw date {label!r}") from exc

    return (
        draw_date.isoformat(),
        main_number,
        main_number[-3:],
        first_prize[-2:],
    )


def parse_mlnhngoc_vip(payload: dict) -> tuple[str, str, str, str]:
    """Read Hanoi VIP from mlnhngoc.net's public current-result endpoint."""
    item = payload.get("item")
    label = str(payload.get("label", "")).strip()
    if not isinstance(item, dict):
        raise RuntimeError("mlnhngoc.net: latest draw is incomplete")

    main_number = digits_only(str(item.get("ran26", "")))
    first_prize = digits_only(str(item.get("ran0", "")))
    if len(main_number) != 5 or len(first_prize) != 5:
        raise RuntimeError(
            "mlnhngoc.net: special or first prize is not complete"
        )
    try:
        draw_date = datetime.strptime(label, "%d-%m-%Y").date()
    except ValueError as exc:
        raise RuntimeError(
            f"mlnhngoc.net: invalid draw date {label!r}"
        ) from exc

    return (
        draw_date.isoformat(),
        main_number,
        main_number[-3:],
        first_prize[-2:],
    )


def parse_laodl_result(
    payload: dict,
    expected_date: str,
) -> tuple[str, str, str, str]:
    """Read today's six-digit Lao Development Lottery result."""
    results = payload.get("resultData")
    if not isinstance(results, list):
        raise RuntimeError("laodl.com: result list is missing")

    today_result = next(
        (
            item
            for item in results
            if isinstance(item, dict)
            and str(item.get("roundDate", ""))[:10] == expected_date
        ),
        None,
    )
    if not today_result:
        raise RuntimeError(
            f"laodl.com: no draw dated {expected_date} yet"
        )

    main_number = digits_only(str(today_result.get("winNumber", "")))
    if len(main_number) != 6:
        raise RuntimeError(
            f"laodl.com: draw {expected_date} is waiting for its result"
        )

    return (
        expected_date,
        main_number,
        main_number[-3:],
        main_number[2:4],
    )


def parse_minhngoc_normal(html: str) -> tuple[str, str, str, str]:
    """Read the newest Northern Vietnam draw from Minh Ngoc.

    Giải ĐB is the five-digit main result. The top result is its final three
    digits, while the bottom result is the final two digits of Giải nhất.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    date_match = re.search(
        r"KẾT\s*QUẢ\s*XỔ\s*SỐ\s*Miền\s*Bắc\s*-\s*"
        r"(\d{2}/\d{2}/\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    special_match = re.search(
        r"Giải\s*ĐB\s*(\d{5})",
        text,
        flags=re.IGNORECASE,
    )
    first_match = re.search(
        r"Giải\s*nhất\s*(\d{5})",
        text,
        flags=re.IGNORECASE,
    )
    if not (date_match and special_match and first_match):
        raise RuntimeError("Minh Ngoc: latest draw is incomplete")

    draw_date = datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
    main_number = special_match.group(1)
    top3 = main_number[-3:]
    bottom2 = first_match.group(1)[-2:]
    return draw_date.isoformat(), main_number, top3, bottom2


def require_current_direct_date(
    key: str,
    draw_date: str,
    now: datetime,
) -> None:
    """Reject a stale direct result instead of publishing it as today's draw."""
    expected = now.date().isoformat()
    if draw_date != expected:
        raise RuntimeError(
            f"{key}: source draw date is {draw_date}; waiting for {expected}"
        )


def extract_numbers(soup: BeautifulSoup) -> list[str]:
    for selector in RESULT_SELECTORS:
        numbers = [
            digits_only(element.get_text(" ", strip=True))
            for element in soup.select(selector)
        ]
        numbers = [value for value in numbers if 2 <= len(value) <= 6]
        if len(numbers) >= 2:
            return numbers

    candidates: list[str] = []
    main = soup.select_one("main")
    if main:
        for element in main.select("div, span, p"):
            value = element.get_text(" ", strip=True)
            if re.fullmatch(r"\d{2,6}", value):
                candidates.append(value)
    return list(dict.fromkeys(candidates))


def extract_draw_date(soup: BeautifulSoup, fallback: datetime) -> str:
    heading = soup.select_one("h1")
    heading_text = heading.get_text(" ", strip=True) if heading else ""
    match = re.search(r"(\d{1,2})\s+([ก-๙]+)\s+(\d{4})", heading_text)
    if not match or match.group(2) not in THAI_MONTHS:
        return fallback.date().isoformat()
    day, month_name, year = match.groups()
    christian_year = int(year) - 543 if int(year) > 2400 else int(year)
    return datetime(
        christian_year,
        THAI_MONTHS[month_name],
        int(day),
    ).date().isoformat()


def normalize_result(key: str, numbers: list[str]) -> tuple[str, str, str]:
    if key in {"government", "lao"}:
        main = next((number for number in numbers if len(number) == 6), "")
    else:
        main = next((number for number in numbers if len(number) == 5), "")

    top3 = next((number for number in numbers if len(number) == 3), "")
    bottom2 = next((number for number in numbers if len(number) == 2), "")

    if not main and top3 and bottom2:
        main = f"{top3}{bottom2}"
    if not top3 and main:
        top3 = main[-3:]
    if not bottom2 and main:
        bottom2 = main[-2:]
    if not (main and top3 and bottom2):
        raise RuntimeError(f"ข้อมูลไม่ครบ: {numbers!r}")
    return main, top3, bottom2


def correct_dow_draw_date(
    draw_date: str,
    now: datetime,
    numbers_changed: bool = True,
) -> str:
    """Correct ExpHuay's occasional one-day-stale DJI heading.

    The Dow result shown early Tuesday-Saturday Thailand time belongs to the
    previous calendar day. Sunday and Monday are intentionally excluded.
    """
    if (
        not numbers_changed
        or now.weekday() not in {1, 2, 3, 4, 5}
    ):
        return draw_date

    expected = (now.date() - timedelta(days=1)).isoformat()
    if draw_date < expected:
        print(
            "[dow] แก้วันที่งวดจาก "
            f"{draw_date} เป็น {expected} (เวลาประเทศไทย {now:%Y-%m-%d %H:%M})"
        )
        return expected
    return draw_date


def correct_nikkei_morning_draw_date(
    draw_date: str,
    now: datetime,
    numbers_changed: bool = True,
) -> str:
    """Use today's date when today's Nikkei morning result is already out.

    ExpHuay can briefly return the new result numbers with the previous date
    still present in the rendered heading.
    """
    if (
        not numbers_changed
        or now.weekday() > 4
        or (now.hour, now.minute) < (9, 30)
    ):
        return draw_date

    expected = now.date().isoformat()
    if draw_date < expected:
        print(
            "[nikkei_morning] แก้วันที่งวดจาก "
            f"{draw_date} เป็น {expected} "
            f"(เวลาประเทศไทย {now:%Y-%m-%d %H:%M})"
        )
        return expected
    return draw_date


def correct_nikkei_afternoon_draw_date(
    draw_date: str,
    now: datetime,
    numbers_changed: bool = True,
) -> str:
    """Use today's date after the weekday Nikkei afternoon draw."""
    if (
        not numbers_changed
        or now.weekday() > 4
        or (now.hour, now.minute) < (13, 0)
    ):
        return draw_date

    expected = now.date().isoformat()
    if draw_date < expected:
        print(
            "[nikkei_afternoon] แก้วันที่งวดจาก "
            f"{draw_date} เป็น {expected} "
            f"(เวลาประเทศไทย {now:%Y-%m-%d %H:%M})"
        )
        return expected
    return draw_date


SAME_DAY_DRAW_RULES = {
    "government": ((16, 0), {0, 1, 2, 3, 4, 5, 6}),
    "lao": ((20, 30), {0, 1, 2, 3, 4}),
    "hanoi_special": ((17, 30), {0, 1, 2, 3, 4, 5, 6}),
    "hanoi_normal": ((18, 30), {0, 1, 2, 3, 4, 5, 6}),
    "hanoi_vip": ((19, 30), {0, 1, 2, 3, 4, 5, 6}),
    "thai_stock": ((16, 45), {0, 1, 2, 3, 4}),
}


def result_differs_from_latest(
    entries: list[dict],
    main: str,
    top3: str,
    bottom2: str,
) -> bool:
    """Return True only when the scraped numbers differ from stored latest."""
    if not entries:
        return True
    latest = max(
        entries,
        key=lambda entry: (
            entry.get("date", ""),
            entry.get("time", ""),
        ),
    )
    return (
        latest.get("main"),
        latest.get("top3"),
        latest.get("bottom2"),
    ) != (main, top3, bottom2)


def was_updated_today(
    data: dict,
    key: str,
    now: datetime,
) -> bool:
    """Recognize a new result saved under yesterday by an older script."""
    meta = data.get("_meta", {})
    if key not in meta.get("updated", []):
        return False
    try:
        last_run = datetime.fromisoformat(meta.get("last_run", ""))
    except (TypeError, ValueError):
        return False
    return last_run.astimezone(THAI_TZ).date() == now.date()


def correct_same_day_draw_date(
    key: str,
    draw_date: str,
    now: datetime,
    numbers_changed: bool,
) -> str:
    """Correct a stale heading only after draw time and with new numbers."""
    rule = SAME_DAY_DRAW_RULES.get(key)
    if not rule or not numbers_changed:
        return draw_date

    draw_time, allowed_weekdays = rule
    if (
        now.weekday() not in allowed_weekdays
        or (now.hour, now.minute) < draw_time
    ):
        return draw_date
    if key == "government" and now.day not in {1, 16}:
        return draw_date

    expected = now.date().isoformat()
    if draw_date < expected:
        print(
            f"[{key}] แก้วันที่งวดจาก {draw_date} เป็น {expected} "
            f"เพราะเลขเปลี่ยนจากงวดเดิม "
            f"(เวลาประเทศไทย {now:%Y-%m-%d %H:%M})"
        )
        return expected
    return draw_date


def remove_recent_duplicate_result(
    entries: list[dict],
    draw_date: str,
    main: str,
    top3: str,
    bottom2: str,
) -> list[dict]:
    """Remove a wrongly dated duplicate when the same DJI result is moved."""
    current_date = datetime.fromisoformat(draw_date).date()
    cleaned: list[dict] = []
    for entry in entries:
        try:
            entry_date = datetime.fromisoformat(entry.get("date", "")).date()
        except (TypeError, ValueError):
            cleaned.append(entry)
            continue
        same_numbers = (
            entry.get("main") == main
            and entry.get("top3") == top3
            and entry.get("bottom2") == bottom2
        )
        is_recent_older_copy = (
            same_numbers
            and entry_date < current_date
            and (current_date - entry_date).days <= 3
        )
        if not is_recent_older_copy:
            cleaned.append(entry)
    return cleaned


def upsert(
    entries: list[dict],
    draw_date: str,
    now: datetime,
    main: str,
    top3: str,
    bottom2: str,
) -> list[dict]:
    entries = [entry for entry in entries if entry.get("date") != draw_date]
    entries.append(
        {
            "date": draw_date,
            "time": now.strftime("%H:%M"),
            "status": "out",
            "main": main,
            "top3": top3,
            "bottom2": bottom2,
        }
    )
    return sorted(
        entries,
        key=lambda entry: (entry.get("date", ""), entry.get("time", "")),
        reverse=True,
    )[:MAX_HISTORY_PER_TYPE]


def save_data(data: dict) -> None:
    with DATA_FILE.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> int:
    api_key = os.environ.get("SCRAPINGANT_API_KEY", "").strip()
    if not api_key:
        print(
            "ไม่พบ GitHub Secret ชื่อ SCRAPINGANT_API_KEY",
            file=sys.stderr,
        )
        return 2
    render_javascript = (
        os.environ.get("SCRAPINGANT_BROWSER", "false").strip().lower()
        == "true"
    )
    requested_keys = [
        key.strip()
        for key in os.environ.get("LOTTERY_KEYS", "").split(",")
        if key.strip()
    ]
    unknown_keys = [key for key in requested_keys if key not in PAGES]
    if unknown_keys:
        print(
            f"ไม่รู้จักประเภทรางวัล: {', '.join(unknown_keys)}",
            file=sys.stderr,
        )
        return 2
    selected_pages = (
        {key: PAGES[key] for key in requested_keys}
        if requested_keys
        else PAGES
    )
    print(
        "โหมดทดลอง: "
        + (
            "เปิด JavaScript (ประมาณ 10 เครดิตต่อหน้า)"
            if render_javascript
            else "ไม่เปิด JavaScript (ประมาณ 1 เครดิตต่อหน้า)"
        )
    )
    print("รายการที่จะดึง: " + ", ".join(selected_pages))

    data = load_data()
    now = datetime.now(THAI_TZ)
    updated: list[str] = []
    errors: dict[str, str] = {}

    for key, url in selected_pages.items():
        try:
            if key == "government":
                try:
                    html = fetch_direct_html(url)
                    draw_date, main_number, top3, bottom2 = (
                        parse_sanook_government(html)
                    )
                    print(
                        "[government] fetched directly from Sanook "
                        "(0 ScrapingAnt credits)"
                    )
                except Exception as direct_error:
                    print(
                        f"[government] direct Sanook request failed ({direct_error}); "
                        "retrying through ScrapingAnt...",
                        file=sys.stderr,
                    )
                    html = fetch_html(api_key, url, True)
                    draw_date, main_number, top3, bottom2 = (
                        parse_sanook_government(html)
                    )
            elif key == "lao":
                payload = fetch_direct_json(url)
                draw_date, main_number, top3, bottom2 = parse_laodl_result(
                    payload,
                    now.date().isoformat(),
                )
                print(
                    "[lao] fetched directly from laodl.com "
                    "(0 ScrapingAnt credits)"
                )
            elif key == "hanoi_special":
                payload = fetch_direct_json(url)
                draw_date, main_number, top3, bottom2 = (
                    parse_xsthm_special(payload)
                )
                print(
                    "[hanoi_special] fetched directly from xsthm.com "
                    "(0 ScrapingAnt credits)"
                )
            elif key == "hanoi_vip":
                payload = fetch_direct_json(url)
                draw_date, main_number, top3, bottom2 = (
                    parse_mlnhngoc_vip(payload)
                )
                print(
                    "[hanoi_vip] fetched directly from mlnhngoc.net "
                    "(0 ScrapingAnt credits)"
                )
            elif key == "hanoi_normal":
                html = fetch_direct_html(url)
                draw_date, main_number, top3, bottom2 = (
                    parse_minhngoc_normal(html)
                )
                print(
                    "[hanoi_normal] fetched directly from Minh Ngoc "
                    "(0 ScrapingAnt credits)"
                )
            elif key == "dow":
                try:
                    html = fetch_direct_html(url)
                    draw_date, main_number, top3, bottom2 = parse_msn_dow(html)
                    print("[dow] fetched directly from MSN (0 ScrapingAnt credits)")
                except Exception as direct_error:
                    print(
                        f"[dow] direct MSN request failed ({direct_error}); "
                        "retrying through ScrapingAnt...",
                        file=sys.stderr,
                    )
                    html = fetch_html(api_key, url, True)
                    draw_date, main_number, top3, bottom2 = parse_msn_dow(html)
            elif key in {"nikkei_morning", "nikkei_afternoon"}:
                try:
                    html = fetch_direct_html(url)
                    draw_date, main_number, top3, bottom2 = parse_nikkei_225(html)
                    print(
                        f"[{key}] fetched directly from Nikkei 225 official site "
                        "(0 ScrapingAnt credits)"
                    )
                except Exception as direct_error:
                    print(
                        f"[{key}] direct Nikkei request failed ({direct_error}); "
                        "retrying through ScrapingAnt...",
                        file=sys.stderr,
                    )
                    html = fetch_html(api_key, url, True)
                    draw_date, main_number, top3, bottom2 = parse_nikkei_225(html)
            elif key == "thai_stock":
                try:
                    set50_html = fetch_direct_html(SET50_URL)
                    set_html = fetch_direct_html(url)
                    draw_date, main_number, top3, bottom2 = parse_set_thai_stock(
                        set50_html,
                        set_html,
                    )
                    print(
                        "[thai_stock] fetched directly from SET50 and SET "
                        "(0 ScrapingAnt credits)"
                    )
                except Exception as direct_error:
                    print(
                        f"[thai_stock] direct SET request failed ({direct_error}); "
                        "retrying through ScrapingAnt...",
                        file=sys.stderr,
                    )
                    set50_html = fetch_html(api_key, SET50_URL, True)
                    set_html = fetch_html(api_key, url, True)
                    draw_date, main_number, top3, bottom2 = parse_set_thai_stock(
                        set50_html,
                        set_html,
                    )
            else:
                html = fetch_html(api_key, url, render_javascript)
                soup = BeautifulSoup(html, "html.parser")
                title = (
                    soup.title.get_text(" ", strip=True)
                    if soup.title
                    else ""
                )
                if (
                    "รอสักครู่" in title
                    or "just a moment" in title.lower()
                ):
                    raise RuntimeError("เว็บไซต์ต้นทางแสดงหน้าป้องกันบอต")
                numbers = extract_numbers(soup)
                if len(numbers) < 2:
                    raise RuntimeError(
                        f"ไม่พบชุดผลรางวัล (title={title!r})"
                    )
                draw_date = extract_draw_date(soup, now)
                main_number, top3, bottom2 = normalize_result(key, numbers)
            if key in {
                "government",
                "lao",
                "hanoi_special",
                "hanoi_normal",
                "hanoi_vip",
                "nikkei_morning",
                "nikkei_afternoon",
                "thai_stock",
            }:
                require_current_direct_date(key, draw_date, now)
            numbers_changed = result_differs_from_latest(
                data[key],
                main_number,
                top3,
                bottom2,
            ) or was_updated_today(data, key, now)
            if key == "dow":
                data[key] = remove_recent_duplicate_result(
                    data[key],
                    draw_date,
                    main_number,
                    top3,
                    bottom2,
                )
            elif key == "nikkei_morning":
                draw_date = correct_nikkei_morning_draw_date(
                    draw_date,
                    now,
                    numbers_changed,
                )
                data[key] = remove_recent_duplicate_result(
                    data[key],
                    draw_date,
                    main_number,
                    top3,
                    bottom2,
                )
            elif key == "nikkei_afternoon":
                draw_date = correct_nikkei_afternoon_draw_date(
                    draw_date,
                    now,
                    numbers_changed,
                )
                data[key] = remove_recent_duplicate_result(
                    data[key],
                    draw_date,
                    main_number,
                    top3,
                    bottom2,
                )
            elif key in SAME_DAY_DRAW_RULES:
                draw_date = correct_same_day_draw_date(
                    key,
                    draw_date,
                    now,
                    numbers_changed,
                )
                data[key] = remove_recent_duplicate_result(
                    data[key],
                    draw_date,
                    main_number,
                    top3,
                    bottom2,
                )
            data[key] = upsert(
                data[key],
                draw_date,
                now,
                main_number,
                top3,
                bottom2,
            )
            updated.append(key)
            print(
                f"[{key}] สำเร็จ: "
                f"{draw_date} / {main_number} / {top3} / {bottom2}"
            )
        except Exception as exc:
            errors[key] = str(exc)
            print(f"[{key}] ไม่สำเร็จ: {exc}", file=sys.stderr)

    data["_meta"] = {
        "provider": "scrapingant",
        "render_javascript": render_javascript,
        "requested": list(selected_pages),
        "last_run": now.isoformat(timespec="seconds"),
        "updated": updated,
        "errors": errors,
    }
    save_data(data)

    print(f"สรุป: สำเร็จ {len(updated)}/{len(selected_pages)} หน้า")
    return 0 if updated else 1


if __name__ == "__main__":
    raise SystemExit(main())
