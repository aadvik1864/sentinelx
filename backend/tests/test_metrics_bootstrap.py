from datetime import UTC, datetime, timedelta

from app.models import DetectionRule
from app.seed import bootstrap
from tests.test_pipeline import event, send


def test_dashboard_chart_includes_the_partial_first_hour(client, tokens):
    now = datetime.now(UTC)
    oldest = now - timedelta(hours=24) + timedelta(seconds=5)
    send(client, tokens, event(timestamp=oldest.isoformat(), event_type="system_event"))
    response = client.get("/api/v1/dashboard", headers=tokens["viewer"])
    metrics = response.json()
    assert metrics["total_events"] == 1
    assert sum(item["events"] for item in metrics["activity"]) == 1


def test_bootstrap_does_not_recreate_intentionally_deleted_rules(client, tokens, db):
    rule = db.query(DetectionRule).filter(DetectionRule.kind == "threshold").one()
    rule_id = rule.id
    assert client.delete(f"/api/v1/rules/{rule_id}", headers=tokens["admin"]).status_code == 204
    db.expire_all()
    bootstrap(db)
    assert db.query(DetectionRule).filter(DetectionRule.id == rule_id).first() is None
