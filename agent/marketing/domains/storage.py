"""Marketing repositories over the Hermes-owned ``state.db``."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from agent.marketing.data_paths import MarketingDataPaths


class MarketingDomainRepository:
    """Base class for repositories sharing the product business-state DB."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        self.paths = paths or MarketingDataPaths.from_env()
        from hermes_state import SessionDB

        owner = SessionDB(db_path=self.paths.agent_db)
        owner.close()

    def _connect(self) -> sqlite3.Connection:
        # SessionDB owns schema and data migrations. Repositories retain a
        # small SQL seam for domain queries but never choose another database.
        self.paths.agent_db.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.paths.agent_db, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db
