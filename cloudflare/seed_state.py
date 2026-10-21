"""Create an ignored D1 import file from a consistent local data snapshot."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import uuid
import zlib

from state_client import MAX_FILE_SIZE, ROOT, StateClient, data_files


SQL_CHUNK = 24 * 1024
OUTPUT = ROOT / "cloudflare" / "state_seed.sql"


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_seed(output: Path = OUTPUT) -> tuple[int, int]:
    client = StateClient()
    file_count = 0
    byte_count = 0
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for path in data_files():
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
            raw = client._read_stable(path)
            if not raw:
                continue
            relative = path.relative_to(ROOT).as_posix()
            version = str(uuid.uuid4())
            digest = hashlib.sha256(raw).hexdigest()
            compressed = zlib.compress(raw, level=6)
            chunks = [compressed[i:i + SQL_CHUNK]
                      for i in range(0, len(compressed), SQL_CHUNK)]
            for index, chunk in enumerate(chunks):
                stream.write(
                    "INSERT OR REPLACE INTO state_chunks(path,version,chunk_index,payload) "
                    f"VALUES({sql_quote(relative)},{sql_quote(version)},{index},X'{chunk.hex()}');\n"
                )
            stream.write(
                "INSERT OR REPLACE INTO state_files(path,version,byte_size,sha256,chunk_count) "
                f"VALUES({sql_quote(relative)},{sql_quote(version)},{len(raw)},{sql_quote(digest)},{len(chunks)});\n"
            )
            stream.write(
                f"DELETE FROM state_chunks WHERE path={sql_quote(relative)} "
                f"AND version<>{sql_quote(version)};\n"
            )
            file_count += 1
            byte_count += len(raw)
    return file_count, byte_count


if __name__ == "__main__":
    count, size = build_seed()
    print(f"Created D1 seed for {count} files ({size} raw bytes) at {OUTPUT}")
