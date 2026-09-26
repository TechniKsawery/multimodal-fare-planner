#!/usr/bin/env python3
"""Sesja 1: pobranie GTFS (PL + DE) i OSM (PL + NRW) oraz weryfikacja integralności.

Użycie:  python scripts/fetch_data.py [katalog_danych]   (domyślnie ./data)
Działa na Windowsie, Linuksie i macOS, wymaga tylko Pythona 3.8+.
"""
import hashlib, os, shutil, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "data")

GTFS = {
    # PolishTrainsGTFS (Mikołaj Kuranowski): wszyscy przewoźnicy kolejowi w PL
    "gtfs/pl/polish_trains.zip": "https://mkuran.pl/gtfs/polish_trains.zip",
    # gtfs.de: dalekobieżne (FV) i koleje regionalne (RV) całych Niemiec, NRW jest w środku
    "gtfs/de/de_fv.zip": "https://download.gtfs.de/germany/fv_free/latest.zip",
    "gtfs/de/de_rv.zip": "https://download.gtfs.de/germany/rv_free/latest.zip",
    # mkuran.pl: komunikacja miejska ZTM Lublin (ZDiTM), CC0
    "gtfs/pl/lublin.zip": "https://mkuran.pl/gtfs/lublin.zip",
}
OSM = {
    "osm/poland-latest.osm.pbf": "https://download.geofabrik.de/europe/poland-latest.osm.pbf",
    "osm/nordrhein-westfalen-latest.osm.pbf":
        "https://download.geofabrik.de/europe/germany/nordrhein-westfalen-latest.osm.pbf",
}
# Część serwerów (np. mkuran.pl) odrzuca domyślny User-Agent urllib kodem 403
UA = {"User-Agent": "multimodal-fare-planner/0.1 (+https://github.com/TechniKsawery/multimodal-fare-planner)"}


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={**UA, **({"Range": f"bytes={have}-"} if have else {})})
    print(f">> {url}")
    with urllib.request.urlopen(req) as r:
        mode = "ab" if have and r.status == 206 else "wb"
        with open(part, mode) as f:
            shutil.copyfileobj(r, f, 1 << 20)
    part.replace(dest)
    print(f"   {dest.relative_to(DATA)}: {dest.stat().st_size / 1e6:.1f} MB")


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ok = True
    for rel, url in {**GTFS, **OSM}.items():
        download(url, DATA / rel)

    print("\n== MD5 OSM (sumy z Geofabrik)")
    for rel, url in OSM.items():
        with urllib.request.urlopen(urllib.request.Request(url + ".md5", headers=UA)) as r:
            expected = r.read().decode().split()[0]
        got = md5(DATA / rel)
        good = got == expected
        ok &= good
        print(f"   {rel}: {'OK' if good else f'BŁĄD (jest {got}, powinno być {expected})'}")

    print("\n== Walidacja GTFS")
    zips = [str(DATA / rel) for rel in GTFS]
    res = subprocess.run([sys.executable, str(ROOT / "check_gtfs.py"), *zips],
                         capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    print(res.stdout, res.stderr, sep="")
    (DATA / "gtfs" / "REPORT.txt").write_text(res.stdout, encoding="utf-8")
    ok &= res.returncode == 0

    print("\n== Rozmiary")
    for p in sorted(DATA.rglob("*")):
        if p.is_file():
            print(f"   {p.stat().st_size / 1e6:10.1f} MB  {p.relative_to(DATA)}")
    print("\nWSZYSTKO OK" if ok else "\nSĄ BŁĘDY, patrz wyżej")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
