import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    busy_timeout_ms: int = 2000


def load_settings() -> Settings:
    raw_path = os.getenv("ECG_AGENT_DB_PATH", "var/ecg_evidence.db")
    raw_timeout = os.getenv("ECG_AGENT_DB_BUSY_TIMEOUT_MS", "2000")
    try:
        timeout = int(raw_timeout)
    except ValueError as exc:
        raise ValueError(
            "ECG_AGENT_DB_BUSY_TIMEOUT_MS must be an integer between 100 and 30000"
        ) from exc
    if not 100 <= timeout <= 30_000:
        raise ValueError(
            "ECG_AGENT_DB_BUSY_TIMEOUT_MS must be between 100 and 30000"
        )
    return Settings(database_path=Path(raw_path), busy_timeout_ms=timeout)
