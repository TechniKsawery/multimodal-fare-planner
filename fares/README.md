English | Polski: [Polish version](README.pl.md)

# Fares module (`fares/`)

This module estimates the price of individual journey segments. It supports
rail and local transport fares for Poland and Germany, including:

- PKP Intercity and German DB rail fares;
- cross-border Poland–Germany rail estimates;
- VRR, BVG/VBB Berlin, HVV Hamburg, MVV Munich and VRS/Cologne tariffs;
- ZTM Lublin and other selected local rail and public-transport fares;
- FlixBus prices and documented fallback estimates;
- passenger profiles, age discounts, BahnCards, city cards and verified source
  metadata.

The routing layer selects the appropriate calculator in
`routing/pricing.py`. Every result carries a price type and verification
status. Official values must include a source URL and verification date;
unverified values remain explicitly marked as estimates.

The detailed technical record, including fare tables, limitations, research
notes and examples, is maintained in the [Polish documentation](README.pl.md).
Code identifiers, data field names and source quotations remain unchanged
there so that the documentation can be checked directly against the
implementation.

## Important limitations

- Prices are estimates unless explicitly marked as official.
- Dynamic carrier prices and incomplete zone mappings can reduce accuracy.
- Third-party feeds, tariffs and data retain their own licences.
- Never add a fare, discount or partner without a primary source and a
  verification date.

See [`DATA_SOURCES.md`](../DATA_SOURCES.md) for feed licences and
[`CONTRIBUTING.md`](../CONTRIBUTING.md) for data-verification rules.
