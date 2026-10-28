#!/usr/bin/env python3
"""Rebuild stored Nikkei afternoon lottery results from official daily closes."""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import os
import tempfile
from bisect import bisect_left
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import Request, urlopen


OFFICIAL_DAILY_CSV_URL = (
    "https://indexes.nikkei.co.jp/nkave/historical/"
    "nikkei_stock_average_daily_en.csv"
)
TWO_PLACES = Decimal("0.01")


def parse_daily_closes(csv_text: str) -> dict[str, Decimal]:
    """Return ISO dates mapped to official closes from Nikkei's daily CSV."""
    closes: dict[str, Decimal] = {}
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames or "Date of Data" not in reader.fieldnames or "Close" not in reader.fieldnames:
        raise ValueError("CSV must contain 'Date of Data' and 'Close' columns")

    for row in reader:
        raw_date = (row.get("Date of Data") or "").strip()
        try:
            parsed_date = datetime.strptime(raw_date, "%Y/%m/%d").date()
        except ValueError:
            # The official file ends with a prose note rather than a data row.
            continue
        raw_close = (row.get("Close") or "").strip().replace(",", "")
        try:
            close = Decimal(raw_close).quantize(TWO_PLACES)
        except InvalidOperation as exc:
            raise ValueError(f"invalid close for {raw_date}: {raw_close!r}") from exc
        iso_date = parsed_date.isoformat()
        if iso_date in closes and closes[iso_date] != close:
            raise ValueError(
                f"conflicting duplicate close for {iso_date}: "
                f"{closes[iso_date]} and {close}"
            )
        closes[iso_date] = close

    if not closes:
        raise ValueError("official CSV contains no valid daily closes")
    return closes


def calculate_result(
    close: Decimal,
    previous_close: Decimal,
) -> tuple[str, str, str]:
    """Return main, top3 and bottom2 for one official afternoon close."""
    normalized_close = close.quantize(TWO_PLACES)
    integer, decimals = f"{normalized_close:.2f}".split(".")
    top3 = integer[-1] + decimals

    change = (normalized_close - previous_close.quantize(TWO_PLACES)).quantize(
        TWO_PLACES
    )
    change_decimals = f"{abs(change):.2f}".split(".")[1]
    bottom2 = change_decimals
    return top3 + bottom2, top3, bottom2


def backfill(
    data: dict,
    closes: dict[str, Decimal],
) -> tuple[dict, list[dict]]:
    """Return a copied dataset with only Nikkei afternoon numbers rebuilt."""
    entries = data.get("nikkei_afternoon")
    if not isinstance(entries, list):
        raise ValueError("results data has no nikkei_afternoon list")

    trading_dates = sorted(closes)
    calculated: list[tuple[str, str, str]] = []
    for entry in entries:
        draw_date = entry.get("date", "") if isinstance(entry, dict) else ""
        position = bisect_left(trading_dates, draw_date)
        if position >= len(trading_dates) or trading_dates[position] != draw_date:
            raise ValueError(f"official close missing for {draw_date or '<blank date>'}")
        if position == 0:
            raise ValueError(f"previous trading close missing for {draw_date}")
        calculated.append(
            calculate_result(
                closes[draw_date],
                closes[trading_dates[position - 1]],
            )
        )

    updated = copy.deepcopy(data)
    audit: list[dict] = []
    for entry, (main, top3, bottom2) in zip(
        updated["nikkei_afternoon"], calculated, strict=True
    ):
        old = {
            "main": entry.get("main"),
            "top3": entry.get("top3"),
            "bottom2": entry.get("bottom2"),
        }
        new = {"main": main, "top3": top3, "bottom2": bottom2}
        if old != new:
            audit.append({"date": entry["date"], "old": old, "new": new})
        entry.update(new)
    return updated, audit


def download_official_csv(url: str = OFFICIAL_DAILY_CSV_URL) -> str:
    request = Request(url, headers={"User-Agent": "9kao9-lottery-backfill/1.0"})
    with urlopen(request, timeout=60) as response:
        return decode_official_csv(response.read())


def decode_official_csv(raw: bytes) -> str:
    """Decode Nikkei's CSV, whose Japanese footer may use CP932."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp932")


def write_json_atomic(path: Path, data: dict) -> None:
    path = path.resolve()
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(data, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results.json"))
    parser.add_argument("--csv", type=Path, help="use a downloaded official CSV")
    parser.add_argument(
        "--write",
        action="store_true",
        help="write changes atomically; otherwise only print the audit",
    )
    args = parser.parse_args()

    csv_text = (
        decode_official_csv(args.csv.read_bytes())
        if args.csv
        else download_official_csv()
    )
    original = json.loads(args.results.read_text(encoding="utf-8"))
    updated, audit = backfill(original, parse_daily_closes(csv_text))

    for change in audit:
        print(
            f"{change['date']}: "
            f"{change['old']['main']} -> {change['new']['main']}"
        )
    print(f"สรุป: เปลี่ยน {len(audit)} งวด จากทั้งหมด {len(updated['nikkei_afternoon'])} งวด")
    if args.write:
        write_json_atomic(args.results, updated)
        print(f"บันทึกแล้ว: {args.results}")
    else:
        print("ยังไม่ได้เขียนไฟล์ (ใช้ --write เมื่อตรวจสอบพร้อมแล้ว)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
