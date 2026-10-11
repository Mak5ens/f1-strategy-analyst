"""Race data: ingestion from FastF1, OpenF1 and Jolpica-F1 into the lake, and SQL access to it with DuckDB."""

import duckdb

from core.lake import Lake
from f1.data.schema import TABLES


def connect(lake: Lake | None = None) -> duckdb.DuckDBPyConnection:
    """DuckDB with one view per table of the lake: `connect().sql("SELECT * FROM laps WHERE season = 2025")`."""
    return (lake or Lake()).connect(TABLES)
