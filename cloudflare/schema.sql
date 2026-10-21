CREATE TABLE IF NOT EXISTS state_files (
  path TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  chunk_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS state_chunks (
  path TEXT NOT NULL,
  version TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  payload BLOB NOT NULL,
  PRIMARY KEY (path, version, chunk_index)
);
