import pytest

from routing import motis_client


@pytest.fixture(autouse=True)
def _clean_geocode_cache():
    """Pamięć podręczna geokodera jest globalna w procesie; testy podstawiają własne odpowiedzi
    geokodera, więc każdy test zaczyna z pustą."""
    motis_client.clear_geocode_cache()
    yield
    motis_client.clear_geocode_cache()
