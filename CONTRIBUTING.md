English | Polski: [wersja polska](CONTRIBUTING.pl.md)

# Contributing

The project welcomes fixes and improvements from the community. Changes must
comply with the [PolyForm Noncommercial License 1.0.0](LICENSE). Authors retain
copyright in their original contributions, and their authorship should be
visible in the GitHub history and pull request description.

Before submitting a pull request, make sure that you have the right to share
the change and that it contains no API keys, private data, or materials under
an incompatible licence. A contribution does not change the licence of the
project's existing code.

## Before merging

- CI (`.github/workflows/tests.yml`) runs `pytest` on every pull request to `main`.
  It must be green. Tests requiring MOTIS are skipped in CI, so a green CI is NOT
  proof that the results match reality.
- `tests/test_data_consistency.py` enforces data rules: every discounted price has
  an age or status boundary, every verified price has a source (URL) and date,
  a city card without verified existence is excluded from recommendations, and
  currencies are not mixed. When adding data, do not add exceptions to `KNOWN_*`
  lists—complete the record.

## A large change requires a live test BEFORE merging

A large change includes, among other things: a new city or data category, a
change to the price/discount/card calculator, a routing or MOTIS configuration
change, or a change combining several PRs.

Before merging such a change, run it against real MOTIS (`docker compose up`,
then `demo.py` or the UI) and live-check several routes and prices against the
operator's official tariff. Record what was checked and on which routes in the
PR description. Green tests without this check are not sufficient for merging a
large change.

## Source rule

Never guess a price, discount, or partner: provide the source URL and
verification date, or set `price_verified: false`.

## Data from external AI and pasted material

Data and figures from external AI or pasted material from other chats (prices,
discounts, rules, partner names) may be added to the repository only after
verification against a primary source (official tariff, terms, or operator
website). External AI has repeatedly confused figures and documents in this
project. Every price has a `source_url` and verification date; if the source
cannot be checked, the field remains empty or `price_verified: false`.
