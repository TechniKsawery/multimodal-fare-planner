import datetime as dt
import importlib.util
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cgf", Path(__file__).resolve().parent.parent / "scripts" / "check_gtfs_freshness.py"
)
cgf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cgf)


def test_last_service_date(tmp_path):
    p = tmp_path / "f.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("calendar.txt", "service_id,end_date\na,20261020\n")
        z.writestr("calendar_dates.txt", "service_id,date\na,20261025\n")
    assert cgf.last_service_date(p) == dt.date(2026, 10, 25)
