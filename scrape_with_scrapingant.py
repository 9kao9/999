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
    "government": "https://exphuay.com/result/goverment",
    "lao": "https://exphuay.com/result/laosdevelops",
    "hanoi_special": "https://exphuay.com/result/xsthm",
    "hanoi_normal": "https://exphuay.com/result/minhngoc",
    "hanoi_vip": "https://exphuay.com/result/mlnhngo",
    "dow": "https://exphuay.com/result/dji",
    "nikkei_morning": "https://exphuay.com/result/nikkei-morning",
    "nikkei_afternoon": "https://exphuay.com/result/nikkei-afternoon",
    "thai_stock": "https://exphuay.com/result/set",
}

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
    response = requests.get(
        SCRAPINGANT_ENDPOINT,
        params={
            "x-api-key": api_key,
            "url": target_url,
            "browser": "true" if render_javascript else "false",
            "timeout": "60",
        },
        timeout=90,
    )
    if not response.ok:
        detail = response.text.strip().replace("\n", " ")[:500]
        raise RuntimeError(
            f"ScrapingAnt HTTP {response.status_code}: {detail}"
        )
    return response.text


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
    print(
        "โหมดทดลอง: "
        + (
            "เปิด JavaScript (ประมาณ 10 เครดิตต่อหน้า)"
            if render_javascript
            else "ไม่เปิด JavaScript (ประมาณ 1 เครดิตต่อหน้า)"
        )
    )

    data = load_data()
    now = datetime.now(THAI_TZ)
    updated: list[str] = []
    errors: dict[str, str] = {}

    for key, url in PAGES.items():
        try:
            html = fetch_html(api_key, url, render_javascript)
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            if "รอสักครู่" in title:
                raise RuntimeError("เว็บไซต์ต้นทางแสดงหน้าป้องกันบอต")
            numbers = extract_numbers(soup)
            if len(numbers) < 2:
                raise RuntimeError(
                    f"ไม่พบชุดผลรางวัล (title={title!r})"
                )
            draw_date = extract_draw_date(soup, now)
            main_number, top3, bottom2 = normalize_result(key, numbers)
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
                f"{main_number} / {top3} / {bottom2}"
            )
        except Exception as exc:
            errors[key] = str(exc)
            print(f"[{key}] ไม่สำเร็จ: {exc}", file=sys.stderr)

    data["_meta"] = {
        "provider": "scrapingant",
        "render_javascript": render_javascript,
        "last_run": now.isoformat(timespec="seconds"),
        "updated": updated,
        "errors": errors,
    }
    save_data(data)

    print(f"สรุป: สำเร็จ {len(updated)}/{len(PAGES)} หน้า")
    return 0 if updated else 1


if __name__ == "__main__":
    raise SystemExit(main())
