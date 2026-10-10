import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal, engine
from app.models import Alert, Event, Incident
from app.schemas import EventInput
from app.services.detection.engine import ingest


def ingest_worker(index):
    # Independent processes have independent Python locks: PostgreSQL must serialize the group.
    with SessionLocal() as db:
        return ingest(
            db,
            EventInput(
                timestamp=datetime.now(UTC),
                source="linux",
                event_type="authentication_failure",
                severity="medium",
                source_ip="203.0.113.88",
                hostname="concurrency-lab",
                username="admin",
                message=f"Concurrent failure {index}",
            ),
        )


@pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="Cross-process advisory locks require PostgreSQL"
)
def test_cross_process_group_has_one_alert_and_one_incident(client, db):
    with ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        results = list(pool.map(ingest_worker, range(15)))
    assert sum(len(row["alerts"]) for row in results) == 1
    assert db.scalar(select(func.count()).select_from(Event)) == 15
    assert db.scalar(select(func.count()).select_from(Alert)) == 1
    assert db.scalar(select(func.count()).select_from(Incident)) == 1
