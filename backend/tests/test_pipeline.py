from datetime import UTC, datetime, timedelta

from app.models import AuditLog

BASE_TIME = datetime.now(UTC) - timedelta(seconds=150)


def event(index=0, **changes):
    return {
        "timestamp": (BASE_TIME + timedelta(seconds=index)).isoformat(),
        "source": "linux",
        "event_type": "authentication_failure",
        "severity": "medium",
        "source_ip": "203.0.113.42",
        "hostname": "linux-lab-01",
        "username": "admin",
        "message": "Failed SSH authentication",
        "metadata": {},
        **changes,
    }


def send(client, tokens, payload):
    response = client.post("/api/v1/events", headers=tokens["analyst"], json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def failures(client, tokens, count=10, **changes):
    return [send(client, tokens, event(index, **changes)) for index in range(count)]


def test_complete_investigation_flow(client, tokens, db):
    result = failures(client, tokens)
    assert not any(item["alerts"] for item in result[:9])
    assert result[-1]["alerts"][0]["severity"] == "high"
    incident_id = result[-1]["incident_id"]
    success = send(
        client,
        tokens,
        event(15, event_type="authentication_success", severity="low", message="Accepted password"),
    )
    assert success["incident_id"] == incident_id
    assert success["alerts"][0]["severity"] == "critical"
    send(
        client,
        tokens,
        event(16, event_type="privilege_escalation", severity="high", message="sudo /usr/bin/id"),
    )
    detail = client.get(f"/api/v1/incidents/{incident_id}", headers=tokens["analyst"]).json()
    assert detail["severity"] == "critical"
    assert len(detail["alerts"]) == 3
    assert detail["event_total"] == 12
    assert detail["mitre_techniques"] == ["T1078", "T1110", "T1548.003"]
    timestamps = [item["timestamp"] for item in detail["events"]]
    assert timestamps == sorted(timestamps)
    response = client.post(
        f"/api/v1/incidents/{incident_id}/notes",
        headers=tokens["analyst"],
        json={"content": "Verified in isolated lab.", "kind": "evidence"},
    )
    assert response.status_code == 201
    enriched = client.post(f"/api/v1/incidents/{incident_id}/enrich", headers=tokens["analyst"])
    assert enriched.status_code == 200
    assert enriched.json()["items"][0]["reputation"] == "unknown"
    analysis = client.post(
        "/api/v1/ai/analyze-incident", headers=tokens["analyst"], json={"incident_id": incident_id}
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["mode"] == "offline"
    assert "Possible credential compromise" in analysis.json()["likely_attack"]
    assert "No actions were executed" in analysis.json()["notice"]
    resolved = client.patch(
        f"/api/v1/incidents/{incident_id}", headers=tokens["analyst"], json={"status": "resolved"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"]
    assert all(row["status"] == "resolved" for row in resolved.json()["alerts"])
    assert db.query(AuditLog).filter(AuditLog.action == "UPDATE_INCIDENT").count() == 1


def test_alert_suppression(client, tokens):
    result = failures(client, tokens, 15)
    assert sum(len(item["alerts"]) for item in result) == 1
    alerts = client.get("/api/v1/alerts", headers=tokens["analyst"]).json()
    assert alerts["total"] == 1
    assert alerts["items"][0]["event_count"] == 15


def test_window_expiry_and_group_isolation(client, tokens):
    failures(client, tokens, 9, timestamp=(datetime.now(UTC) - timedelta(minutes=10)).isoformat())
    other = send(client, tokens, event(15, hostname="another-host"))
    assert not other["alerts"]
    expired = send(client, tokens, event(timestamp=datetime.now(UTC).isoformat()))
    assert not expired["alerts"]


def test_success_requires_same_user_and_target(client, tokens):
    failures(client, tokens)
    other_user = send(
        client, tokens, event(15, event_type="authentication_success", username="other")
    )
    other_target = send(
        client, tokens, event(16, event_type="authentication_success", hostname="other-host")
    )
    assert not other_user["alerts"]
    assert not other_target["alerts"]


def test_port_scan_counts_distinct_ports(client, tokens):
    for index in range(10):
        result = send(
            client,
            tokens,
            event(
                index,
                source="network",
                event_type="network_connection",
                metadata={"destination_port": 22},
            ),
        )
        assert not result["alerts"]
    for index, port in enumerate([23, 25, 53, 80, 443, 445, 3389]):
        result = send(
            client,
            tokens,
            event(
                index + 10,
                source="network",
                event_type="network_connection",
                metadata={"destination_port": port},
            ),
        )
    assert result["alerts"][0]["title"] == "Port scan pattern"


def test_privileged_activity_without_ip(client, tokens):
    result = send(client, tokens, event(event_type="privilege_escalation", source_ip=None))
    assert result["alerts"][0]["severity"] == "high"


def test_unknown_user_followed_by_success(client, tokens):
    failures(client, tokens, 5, metadata={"invalid_user": True})
    success = send(client, tokens, event(12, event_type="authentication_success"))
    assert [row["title"] for row in success["alerts"]] == ["Unknown user authenticated"]


def test_http_error_ratio_and_configurable_threshold(client, tokens):
    rules = client.get("/api/v1/rules", headers=tokens["admin"]).json()["items"]
    rule = next(row for row in rules if row["kind"] == "http_errors")
    updated = client.patch(
        f"/api/v1/rules/{rule['id']}",
        headers=tokens["admin"],
        json={"threshold": 10, "config": {"error_ratio": 0.3}},
    )
    assert updated.status_code == 200, updated.text
    for index in range(10):
        result = send(
            client,
            tokens,
            event(
                index,
                source="nginx",
                event_type="http_request",
                metadata={"http_status": 500 if index < 3 else 200},
            ),
        )
    assert result["alerts"][0]["title"] == "Excessive HTTP errors"


def test_disabled_rule_does_not_detect(client, tokens):
    rules = client.get("/api/v1/rules", headers=tokens["admin"]).json()["items"]
    rule = next(row for row in rules if row["kind"] == "threshold")
    response = client.patch(
        f"/api/v1/rules/{rule['id']}", headers=tokens["admin"], json={"enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["threshold"] == 10
    assert not any(item["alerts"] for item in failures(client, tokens, 12))


def test_event_search_is_literal_and_paginated(client, tokens):
    failures(client, tokens, 5)
    found = client.get(
        "/api/v1/events",
        headers=tokens["analyst"],
        params={"q": "source_ip:203.0.113.42 severity:medium", "limit": 2, "offset": 2},
    ).json()
    assert found["total"] == 5 and len(found["items"]) == 2
    injection = client.get("/api/v1/events", headers=tokens["analyst"], params={"q": "' OR 1=1 --"})
    assert injection.status_code == 422
    percent = client.get("/api/v1/events", headers=tokens["analyst"], params={"q": "%"}).json()
    assert percent["total"] == 0


def test_manual_incident_deduplicates_evidence_and_assignment(client, tokens):
    result = send(client, tokens, event())
    created = client.post(
        "/api/v1/incidents",
        headers=tokens["analyst"],
        json={
            "title": "Manual review",
            "event_ids": [result["event"]["id"], result["event"]["id"]],
        },
    ).json()
    linked = client.post(
        f"/api/v1/incidents/{created['id']}/events",
        headers=tokens["analyst"],
        json={"event_ids": [result["event"]["id"]]},
    )
    assert linked.json()["event_total"] == 1
    assignees = client.get("/api/v1/users/assignees", headers=tokens["analyst"]).json()["items"]
    assigned = client.patch(
        f"/api/v1/incidents/{created['id']}",
        headers=tokens["analyst"],
        json={"assigned_to": assignees[0]["id"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_name"]
