#!/usr/bin/env python3
"""Audyt pokrycia miast i poprawnosci danych (attractions/city_cards/fares).

Liczy realne wskazniki z plikow danych w repo - nigdy nie zgaduje procentow.
Dziala na biezacym working tree ALBO na zbiorze git refs (np. main + drafty
PR), laczac rekordy po `id` w sume (union) zeby policzyc pokrycie "gdyby
wszystkie drafty byly zmergowane" bez faktycznego mergowania konfliktujacych
plikow JSON.

Uzycie:
    python3 scripts/audit_coverage.py                  # biezacy working tree
    python3 scripts/audit_coverage.py --refs origin/main origin/claude/foo ...
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def git_show(ref: str, path: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None


def load_json_from_ref(ref: str | None, path: str):
    if ref is None:
        p = REPO_ROOT / path
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    raw = git_show(ref, path)
    if raw is None:
        return None
    return json.loads(raw)


def _merge_record(existing: dict, item: dict, list_fields: dict[str, str]) -> None:
    """Scala `item` w `existing` in-place: *_verified=True nigdy nie ginie,
    listy wskazane w list_fields (np. {"variants": "id"}) sa scalane rekurencyjnie
    po ich wlasnym id, inne pola uzupelniane tylko jesli brakuje."""
    for field, sub_id_key in list_fields.items():
        if field in item:
            existing_list = existing.setdefault(field, [])
            existing_by_id = {v.get(sub_id_key): v for v in existing_list if sub_id_key in v}
            for sub_item in item[field]:
                sub_key = sub_item.get(sub_id_key)
                if sub_key is None:
                    continue
                if sub_key not in existing_by_id:
                    new_sub = dict(sub_item)
                    existing_list.append(new_sub)
                    existing_by_id[sub_key] = new_sub
                else:
                    sub_existing = existing_by_id[sub_key]
                    for sf in list(sub_item.keys()):
                        if sf.endswith("_verified") and sub_item.get(sf) is True:
                            sub_existing[sf] = True
                        elif sf not in sub_existing:
                            sub_existing[sf] = sub_item[sf]
    for field in list(item.keys()):
        if field in list_fields:
            continue
        if field.endswith("_verified") and item.get(field) is True:
            existing[field] = True
        elif field not in existing:
            existing[field] = item[field]


def collect_union(
    refs: list[str] | None,
    path: str,
    items_key: str,
    id_key: str = "id",
    list_fields: dict[str, str] | None = None,
):
    """Zwraca dict id -> rekord, scalony z wszystkich refs (pierwszy ref tworzy
    rekord, kolejne go uzupelniaja; pole *_verified=True z ktoregokolwiek refu
    nigdy nie jest nadpisywane przez False/brak; listy w list_fields (np.
    warianty karty miejskiej) sa scalane po ich wlasnym id, tym samym
    mechanizmem)."""
    merged: dict[str, dict] = {}
    ref_list = refs if refs else [None]
    list_fields = list_fields or {}
    for ref in ref_list:
        data = load_json_from_ref(ref, path)
        if not data:
            continue
        items = data.get(items_key, [])
        for item in items:
            key = item.get(id_key)
            if key is None:
                continue
            if key not in merged:
                merged[key] = dict(item)
                for field, sub_id_key in list_fields.items():
                    if field in merged[key]:
                        merged[key][field] = [dict(v) for v in merged[key][field]]
            else:
                _merge_record(merged[key], item, list_fields)
    return merged


def audit_attractions(refs: list[str] | None):
    merged = collect_union(refs, "attractions/data/attractions.json", "atrakcje")
    by_city: dict[str, dict] = {}
    for a in merged.values():
        c = a.get("city", "?")
        bucket = by_city.setdefault(c, {"total": 0, "price_verified": 0, "field_present": 0})
        bucket["total"] += 1
        if "price_verified" in a:
            bucket["field_present"] += 1
            if a["price_verified"] is True:
                bucket["price_verified"] += 1
    return by_city, merged


def audit_city_cards(refs: list[str] | None):
    merged = collect_union(
        refs, "attractions/data/city_cards.json", "karty", list_fields={"variants": "id"}
    )
    by_city: dict[str, dict] = {}
    for card in merged.values():
        c = card.get("city", "?")
        bucket = by_city.setdefault(
            c,
            {
                "cards": 0,
                "existence_verified_field_present": 0,
                "existence_verified_true": 0,
                "variants_total": 0,
                "variants_price_verified": 0,
                "variants_field_present": 0,
            },
        )
        bucket["cards"] += 1
        if "existence_verified" in card:
            bucket["existence_verified_field_present"] += 1
            if card["existence_verified"] is True:
                bucket["existence_verified_true"] += 1
        for v in card.get("variants", []):
            bucket["variants_total"] += 1
            if "price_verified" in v:
                bucket["variants_field_present"] += 1
                if v["price_verified"] is True:
                    bucket["variants_price_verified"] += 1
    return by_city, merged


def audit_fares(refs: list[str] | None):
    """fares/data/*.json nie ma jednego wspolnego pliku listujacego miasta -
    kazdy plik to osobny przewoznik/system. Liczymy obecnosc pola `_zrodlo`
    (link+kontekst weryfikacji) per plik, per ref, i bierzemy sume plikow
    jakie w ogole istnieja w ktoryms z refow (unia po nazwie pliku)."""
    ref_list = refs if refs else [None]
    files: dict[str, dict] = {}
    for ref in ref_list:
        if ref is None:
            paths = [p.name for p in (REPO_ROOT / "fares/data").glob("*.json")]
        else:
            out = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", ref, "--", "fares/data"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            ).stdout
            paths = [Path(p).name for p in out.splitlines() if p.endswith(".json")]
        for name in paths:
            data = load_json_from_ref(ref, f"fares/data/{name}")
            if data is None:
                continue
            entry = files.setdefault(name, {"has_source": False})
            src = data.get("_zrodlo")
            if src:
                entry["has_source"] = True
    return files


def pct(n: int, d: int) -> str:
    if d == 0:
        return "n/a"
    return f"{100 * n / d:.0f}%"


def print_report(label: str, refs: list[str] | None):
    print(f"\n=== {label} ===")
    attr_by_city, attr_merged = audit_attractions(refs)
    card_by_city, card_merged = audit_city_cards(refs)
    fares_files = audit_fares(refs)

    print(f"\nAtrakcje: {len(attr_merged)} pozycji total")
    print(f"{'miasto':<15}{'total':>7}{'price_verified=true':>22}{'pole obecne':>14}")
    tot_total = tot_pv = tot_field = 0
    for city, b in sorted(attr_by_city.items()):
        print(f"{city:<15}{b['total']:>7}{pct(b['price_verified'], b['total']):>22}{pct(b['field_present'], b['total']):>14}")
        tot_total += b["total"]
        tot_pv += b["price_verified"]
        tot_field += b["field_present"]
    print(f"{'RAZEM':<15}{tot_total:>7}{pct(tot_pv, tot_total):>22}{pct(tot_field, tot_total):>14}")

    print(f"\nKarty miejskie: {len(card_merged)} kart total")
    print(f"{'miasto':<15}{'kart':>6}{'istnienie=true':>18}{'warianty total':>16}{'wariant price_verif=true':>26}")
    tc = tev = tvt = tvpv = 0
    for city, b in sorted(card_by_city.items()):
        print(
            f"{city:<15}{b['cards']:>6}{pct(b['existence_verified_true'], b['cards']):>18}"
            f"{b['variants_total']:>16}{pct(b['variants_price_verified'], b['variants_total']):>26}"
        )
        tc += b["cards"]
        tev += b["existence_verified_true"]
        tvt += b["variants_total"]
        tvpv += b["variants_price_verified"]
    print(f"{'RAZEM':<15}{tc:>6}{pct(tev, tc):>18}{tvt:>16}{pct(tvpv, tvt):>26}")

    print(f"\nTaryfy transportu (fares/data/*.json): {len(fares_files)} plikow")
    sourced = sum(1 for f in fares_files.values() if f["has_source"])
    for name, f in sorted(fares_files.items()):
        print(f"  {name:<35} _zrodlo obecne: {f['has_source']}")
    print(f"  RAZEM: {sourced}/{len(fares_files)} plikow ma pole _zrodlo ({pct(sourced, len(fares_files))})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refs",
        nargs="*",
        default=None,
        help="Lista git refs do zsumowania (np. origin/main origin/claude/foo). "
        "Bez tej flagi: biezacy working tree.",
    )
    parser.add_argument("--label", default=None)
    args = parser.parse_args()
    label = args.label or (f"refs: {', '.join(args.refs)}" if args.refs else "working tree")
    print_report(label, args.refs)


if __name__ == "__main__":
    main()
