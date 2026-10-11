#!/usr/bin/env python3
"""Sprawdza, ile dni ważności zostało w feedach GTFS (najpóźniejsza data z calendar/calendar_dates).

Użycie: python scripts/check_gtfs_freshness.py [--min-days 3] [--fetch] plik.zip ...
Bez plików: bierze data/gtfs/**/*.zip. Z --fetch: pobiera feedy z fetch_data.GTFS do katalogu tymczasowego.
Kod wyjścia 1, gdy któryś feed wygasa za mniej niż --min-days (lub jest nieczytelny).
"""
import argparse
import csv
import datetime as dt
import io
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def last_service_date(path):
    z = zipfile.ZipFile(path)
    dates = []
    for name, col in (("calendar.txt", "end_date"), ("calendar_dates.txt", "date")):
        if name in z.namelist():
            with z.open(name) as f:
                dates += [r[col] for r in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")) if r.get(col)]
    return dt.datetime.strptime(max(dates), "%Y%m%d").date() if dates else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--min-days", type=int, default=3)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--summary", help="zapisz raport markdown")
    a = ap.parse_args()
    files = [Path(f) for f in a.files]
    if a.fetch:
        sys.path.insert(0, str(ROOT))
        import fetch_data

        tmp = Path(tempfile.mkdtemp())
        for rel, url in fetch_data.GTFS.items():
            dest = tmp / rel
            try:
                fetch_data.DATA = tmp
                fetch_data.download(url, dest)
                files.append(dest)
            except Exception as exc:  # feed niedostępny = też alarm
                print(f"BŁĄD pobierania {rel}: {exc}")
                files.append(Path(rel))
    elif not files:
        files = sorted((ROOT.parent / "data" / "gtfs").rglob("*.zip"))
    today = dt.date.today()
    lines, bad = ["| feed | ważny do | dni |", "|---|---|---|"], False
    for f in files:
        try:
            end = last_service_date(f)
            days = (end - today).days if end else None
        except Exception as exc:
            end, days = f"błąd: {exc}", None
        flag = days is None or days < a.min_days
        bad |= flag
        lines.append(f"| {f.name} | {end} | {days}{' ⚠️' if flag else ''} |")
    report = "\n".join(lines)
    print(report)
    if a.summary:
        Path(a.summary).write_text("## Ważność feedów GTFS\n\n" + report + "\n", encoding="utf-8")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
