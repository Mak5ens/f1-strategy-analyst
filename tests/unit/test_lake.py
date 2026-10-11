from pathlib import Path

import pyarrow as pa
import pytest

from core.lake import Lake, LakeSettings


@pytest.fixture
def lake(tmp_path: Path) -> Lake:
    return Lake(LakeSettings(uri=str(tmp_path / "lake"), _env_file=None))


def test_parquet_round_trip(lake: Lake) -> None:
    table = pa.table({"lap": [1, 2], "time_s": [80.5, 81.0]})
    lake.write_parquet("laps/2025/01-R.parquet", table)
    assert lake.exists("laps/2025/01-R.parquet")
    assert lake.read_parquet("laps/2025/01-R.parquet").equals(table)


def test_rewriting_a_key_replaces_the_file(lake: Lake) -> None:
    lake.write_parquet("laps/2025/01-R.parquet", pa.table({"lap": [1, 2]}))
    lake.write_parquet("laps/2025/01-R.parquet", pa.table({"lap": [3]}))
    assert lake.read_parquet("laps/2025/01-R.parquet").num_rows == 1


def test_json_round_trip_and_missing_key(lake: Lake) -> None:
    assert lake.read_json("_manifest/2025/01.json") is None
    lake.write_json("_manifest/2025/01.json", {"schema_version": 1})
    assert lake.read_json("_manifest/2025/01.json") == {"schema_version": 1}


def test_keys_lists_files_under_a_folder(lake: Lake) -> None:
    assert lake.keys("laps") == []
    lake.write_parquet("laps/2025/02-R.parquet", pa.table({"lap": [1]}))
    lake.write_parquet("laps/2024/01-R.parquet", pa.table({"lap": [1]}))
    assert lake.keys("laps") == ["laps/2024/01-R.parquet", "laps/2025/02-R.parquet"]


def test_connect_creates_a_view_per_table_with_files(lake: Lake) -> None:
    lake.write_parquet("laps/2024/01-R.parquet", pa.table({"season": [2024], "lap": [1]}))
    lake.write_parquet("laps/2025/01-R.parquet", pa.table({"season": [2025, 2025], "lap": [1, 2]}))
    connection = lake.connect(["laps", "results"])
    assert connection.sql("SELECT season, count(*) FROM laps GROUP BY 1 ORDER BY 1").fetchall() == [
        (2024, 1),
        (2025, 2),
    ]
    views = {row[0] for row in connection.sql("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
    assert views == {"laps"}  # no file yet for results: no view rather than a failing one
