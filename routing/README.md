English | Polski: [Polish version](README.pl.md)

# `routing/` — route optimisation engine

The routing engine generates several journey variants for a pair of MOTIS
stops and a travel date. It combines MOTIS itineraries with the fare and flight
modules, calculates price, duration and transfers, checks transfer safety, and
selects recommendations.

Supported variant sources include:

- direct MOTIS rail itineraries;
- alternative origin and destination stops;
- explicitly configured rail hubs using `AlternativeStop`;
- rail–flight–rail and regional flight hubs;
- local public-transport segments priced through `fares/`.

All variants are deduplicated by route signature. A failed alternative is
recorded as a skipped variant instead of aborting the whole search. Hub
detours and repeated stations are filtered using the configured distance and
station-radius limits.

The `checked_baggage` request option affects flight pricing, the landing
buffer, and the minimum flight-to-rail transfer time. These are estimates, not
carrier rules; carrier-specific cabin-baggage limits are outside this module.

The detailed technical record, including hub heuristics, limits, examples and
verification notes, is maintained in the
[Polish documentation](README.pl.md). See [`fares/README.md`](../fares/README.md)
for fare-calculator details.
