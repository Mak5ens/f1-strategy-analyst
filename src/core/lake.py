"""Analytical storage: Parquet files in S3 (or a local folder in tests), queried with DuckDB.

Files are addressed by keys relative to the lake's root, like `<table>/2025/01.parquet`. One folder per table,
so a DuckDB view over `<table>/**/*.parquet` sees the whole table.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb
import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LakeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAKE_", env_file=".env", extra="ignore")

    # `s3://bucket/optional/prefix`, or a local folder.
    uri: str = "data/lake"
    # S3-compatible store outside AWS (SeaweedFS locally), with its scheme: `http://localhost:8334`.
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    s3_region: str = "us-east-1"


class Lake:
    def __init__(self, settings: LakeSettings | None = None) -> None:
        self._settings = settings or LakeSettings()
        self._fs: pafs.FileSystem
        if self._settings.uri.startswith("s3://"):
            self._is_s3 = True
            self._root = self._settings.uri.removeprefix("s3://").strip("/")
            self._fs = pafs.S3FileSystem(**self._s3_options(), allow_bucket_creation=True)
            self._fs.create_dir(self._root.split("/")[0])
        else:
            self._is_s3 = False
            self._root = str(Path(self._settings.uri).resolve())
            self._fs = pafs.LocalFileSystem()
            self._fs.create_dir(self._root, recursive=True)

    def url(self, key: str) -> str:
        """Location of a key for DuckDB: an `s3://` URL or a local path. Globs are allowed."""
        return f"s3://{self._root}/{key}" if self._is_s3 else f"{self._root}/{key}"

    def exists(self, key: str) -> bool:
        return bool(self._fs.get_file_info(self._path(key)).type == pafs.FileType.File)

    def write_parquet(self, key: str, table: pa.Table) -> None:
        self._make_parent(key)
        pq.write_table(table, self._path(key), filesystem=self._fs)

    def read_parquet(self, key: str) -> pa.Table:
        return pq.read_table(self._path(key), filesystem=self._fs)

    def write_json(self, key: str, data: dict[str, Any]) -> None:
        self._make_parent(key)
        with self._fs.open_output_stream(self._path(key)) as stream:
            stream.write(json.dumps(data, indent=2, sort_keys=True).encode())

    def read_json(self, key: str) -> dict[str, Any] | None:
        if not self.exists(key):
            return None
        with self._fs.open_input_stream(self._path(key)) as stream:
            data: dict[str, Any] = json.loads(stream.read())
            return data

    def keys(self, prefix: str) -> list[str]:
        """Every file under a folder, as sorted keys. An empty list if the folder does not exist."""
        selector = pafs.FileSelector(self._path(prefix), recursive=True, allow_not_found=True)
        infos = self._fs.get_file_info(selector)
        return sorted(info.path.removeprefix(self._root + "/") for info in infos if info.type == pafs.FileType.File)

    def export(self, folder: Path) -> int:
        """Copy every file of the lake into a local folder, keys kept: a lake whose `uri` is that folder reads the
        same. Returns the number of files."""
        folder.mkdir(parents=True, exist_ok=True)
        pafs.copy_files(self._root, str(folder.resolve()), source_filesystem=self._fs,
                        destination_filesystem=pafs.LocalFileSystem())  # fmt: skip
        return len(self.keys(""))

    def connect(self, tables: Iterable[str]) -> duckdb.DuckDBPyConnection:
        """An in-memory DuckDB with one view per table that has files, reading `<table>/**/*.parquet`."""
        connection = duckdb.connect()
        connection.execute("SET TimeZone = 'UTC'")  # timestamps come back in UTC, whatever the host's zone
        if self._is_s3:
            self._configure_s3(connection)
        for table in tables:
            if self.keys(table):
                pattern = self.url(f"{table}/**/*.parquet").replace("'", "''")
                connection.execute(
                    f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{pattern}', union_by_name = true)"
                )
        return connection

    def _path(self, key: str) -> str:
        return f"{self._root}/{key.strip('/')}"

    def _make_parent(self, key: str) -> None:
        if not self._is_s3:  # S3 has no folders to create
            self._fs.create_dir(self._path(key).rsplit("/", 1)[0], recursive=True)

    def _s3_options(self) -> dict[str, Any]:
        settings = self._settings
        options: dict[str, Any] = {"region": settings.s3_region}
        if settings.s3_access_key and settings.s3_secret_key:
            options["access_key"] = settings.s3_access_key
            options["secret_key"] = settings.s3_secret_key.get_secret_value()
        if settings.s3_endpoint:
            endpoint = urlparse(settings.s3_endpoint)
            options["endpoint_override"] = endpoint.netloc
            options["scheme"] = endpoint.scheme or "https"
        return options

    def _configure_s3(self, connection: duckdb.DuckDBPyConnection) -> None:
        settings = self._settings
        options = {"TYPE": "s3", "REGION": settings.s3_region, "URL_STYLE": "path"}
        if settings.s3_access_key and settings.s3_secret_key:
            options["KEY_ID"] = settings.s3_access_key
            options["SECRET"] = settings.s3_secret_key.get_secret_value()
        if settings.s3_endpoint:
            endpoint = urlparse(settings.s3_endpoint)
            options["ENDPOINT"] = endpoint.netloc
            options["USE_SSL"] = "true" if endpoint.scheme == "https" else "false"
        body = ", ".join(
            f"{name} {value}" if name in {"TYPE", "USE_SSL"} else f"{name} '{value.replace("'", "''")}'"
            for name, value in options.items()
        )
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
        connection.execute(f"CREATE SECRET lake ({body})")
