English | Polski: [wersja polska](README.pl.md)

# Attractions and city cards module (`attractions/`)

The module provides:
1. A catalogue of recommended places and attractions in destination/transfer cities (including Gelsenkirchen & Ruhrgebiet, Berlin, Kraków, and Lublin).
2. Attraction categories:
   - **Sport** (stadiums, football clubs, sports museums—for example Veltins-Arena Schalke 04, Olympiastadion Berlin, Signal Iduna Park Dortmund)
   - **Tourism & landmarks** (UNESCO sites, castles, museums, architectural icons—for example Museumsinsel, Zeche Zollverein, Wawel)
   - **Entertainment** (viewpoints, modern zoos—for example Berliner Fernsehturm, ZOOM Erlebniswelt)
   - **Food** (iconic flavours and markets—for example Berlin currywurst, Lublin cebularze, Kraków zapiekanki)
   - **Nature** (post-industrial parks, gardens)
3. Suggestions and a value calculator for **City Cards**:
   - **Berlin WelcomeCard** (AB, ABC zones, 72h + Museumsinsel variant)
   - **RUHR.TOPCARD** (annual Ruhr region card—Gelsenkirchen, Essen, Bochum, Dortmund; public transport is NOT included, and it replaced the former WelcomeCard Ruhr, which proved to be a discontinued product)
   - **Kraków Card** (Kraków Tourist Card)
   - Net-savings calculation: whether the card cost pays off for selected attractions and free city transport.
   - A card appears in the calculator and recommendations ONLY when its existence and current operation are confirmed by a source (`existence_verified` + URL + date in `city_cards.json`). At most, the price of an unconfirmed card may be known; its continued existence must never be assumed. `get_all_city_cards()` also shows unconfirmed cards (for data auditing); `get_city_cards()` and the calculator do not.
   - A card discount for an attraction is calculated ONLY where it is recorded: the card's `custom_discounts` (attraction ID -> %) or the attraction's `default_card_discount_percent`. An attraction without an entry receives 0%—there is no “default card discount” (the former `default_discount_percent` could, for example, guess 100% for Wawel Cathedral with Kraków Card). Add a new entry only after source confirmation.
   - **A discount > 0% requires a source field** (`source_url` + `verified_date`, model `DiscountSource`): card `custom_discounts` use `custom_discount_sources` (attraction ID -> source), and attraction `default_card_discount_percent` uses `card_discount_source`. A recorded discount without a complete source is calculated as **0%** and added to `CityCardEvaluation.unverified_discount_attraction_ids` (with “unverified” in `summary`)—the same mechanism as Wawel Cathedral in Kraków Card. An explicit `0.0` in `custom_discounts` means a known lack of discount (no flag). Product-definition exception: `bwc_72h_museumsinsel` gives 100% for Museumsinsel (admission is included in the verified variant price).
   - **Zeroing on 2026-10-12**: discounts without a source field in Berlin, Kraków, Hamburg, Munich, Poznań, and Lublin (16 attractions) were set to zero; the old value remains in `city_cards.json` (`_zerowane_znizki_bez_zrodla_2026_10_12` on the card) and `attractions.json` (`_UWAGA_zniezka_karty`). To restore a discount, enter its value in `custom_discounts` and URL + date in `custom_discount_sources` (or `default_card_discount_percent` + `card_discount_source`); an entry without a source still produces 0%.
   - **Restoration with sources on 2026-10-12** (report `research/zrodla-znizek-kart.md`, branch `gemini/zrodla-znizek`; sources **according to Gemini, not independently verified**—operator domains were unavailable from the cloud). Only discounts clearly confirmed by a quotation and matching base price (10) were restored: Fernsehturm 25%, Olympiastadion 22.7% (8.50 of 11.00 EUR according to the source prices, not the declared 25%), Speicherstadtmuseum 25%, FC Bayern 8%, Residenz 13.3%, Frauenkirche 33.3%, SEA LIFE 20%, Bavaria Filmstadt 10%, Brama Poznania 40%, Fotoplastykon 100%. Euro discounts were converted to percentages only when the base price matched. URL, date, quotation, and notes are in `_zrodla_znizek_2026_10_12` on the card in `city_cards.json`.
     Items that remained at 0% with a flag in that report were resolved by the cross-check below. **Wawel**: explicit `0.0` without a flag—a known lack of discount (krakow.travel: “Does not include visits to Wawel and Wieliczka Salt Mine.”).
   - **Cross-check on 2026-10-12** (report `research/zrodla-krzyzowa-kontrola.md`, branch `gemini/zrodla-krzyz`; **according to Gemini, not independently verified**). Confirmed unchanged: Fernsehturm, Frauenkirche, Residenz, SEA LIFE, Brama Poznania, Fotoplastykon, Speicherstadtmuseum. Resolved items:

     | Attraction | Card | Result |
     |---|---|---|
     | Schindler's Factory | Krakow City Pass | **explicit 0% without a flag**—the product does not include it (sold separately); caveat: variant `krakow_museum_pass_student_3d` was not checked, and 0% applies to all card variants |
     | Museumsinsel | Berlin WelcomeCard Classic | **explicit 0% without a flag**—Classic has no discount; 100% only for variant `bwc_72h_museumsinsel` (code) and “all inclusive” (outside the catalogue) |
     | Lublin Castle | Lublin TripPass | **explicit 0% without a flag**—Pakiet Lubelski has no museum discounts and the castle does not honour the card |
     | IMM Hamburg | Hamburg CARD | normal price corrected **17 → 18 EUR**; with the card 14 EUR = **22.2%** (source imm-hamburg.de/preise-infos/, 2026-10-12). Discounts from the same tariff increased: Ermäßigt 12 → **13 EUR**, Familie 36 → **38 EUR** (marked `price_verified: false`, “according to Gemini, not independently verified”) |
     | Nymphenburg (combo) | München CityTourCard | **0% with an unverified-discount flag.** CityTourCard gives 2 EUR off the combo: **10% in summer** (combo 20 EUR), **12.5% in winter** (combo 16 EUR; the season changes in mid-October). The model has no seasonal prices (`normal_price` 20 EUR is the summer price), so recording the discount requires a seasonal model. 1 EUR off a single palace ticket concerns an item outside the catalogue |

4. Discounts from any basis (age/pupil-student/senior), regardless of whether a city card is held: `best_price_for_attraction(attraction, DiscountProfile(...))` selects the cheapest confirmed price among the standard price and `child_price`/`student_price`/`senior_price`/`family_price` fields (type `GroupPrice`: a specific amount + source + date, never a percentage). Discounts are not combined—we take the minimum.

## Usage

```python
from attractions import get_attractions, evaluate_city_cards, suggest_best_city_card, AttractionCategory

# Pobranie atrakcji sportowych w Berlinie
sport_places = get_attractions(city="Berlin", category=AttractionCategory.SPORT)

# Kalkulacja karty miejskiej dla zestawu wybranych atrakcji + transportu
best_card = suggest_best_city_card(
    city="Berlin",
    selected_attractions=sport_places,
    estimated_transit_cost=15.0,
)
if best_card:
    print(best_card.summary)
```
