"""End-to-end FastAPI integration tests covering Feature 1, Feature 2, CRUD, and simulator APIs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient


def test_health_and_seeded_inventory(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}

    devices = client.get("/api/v1/devices").json()
    hostnames = {d["hostname"] for d in devices}
    assert hostnames == {"uec-abc-prd01", "nx-dc1-core01", "rtr-hq-wan01"}

    important = client.get("/api/v1/important-routes").json()
    assert {r["prefix"] for r in important} == {
        "0.0.0.0/0",
        "10.76.12.0/23",
        "10.127.0.0/16",
        "10.130.0.0/17",
    }


def test_important_routes_crud_and_validation(client: TestClient):
    # Create
    resp = client.post(
        "/api/v1/important-routes",
        json={"prefix": "10.198.0.1/16", "description": "Normalized host bits", "enabled": True},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["prefix"] == "10.198.0.0/16"

    # Duplicate conflict
    dup = client.post(
        "/api/v1/important-routes",
        json={"prefix": "10.198.0.0/16", "description": "Duplicate"},
    )
    assert dup.status_code == 409

    # Invalid CIDR
    bad = client.post("/api/v1/important-routes", json={"prefix": "not-a-cidr"})
    assert bad.status_code == 422

    # Update
    upd = client.put(
        f"/api/v1/important-routes/{created['id']}",
        json={"enabled": False, "description": "Disabled temporarily"},
    )
    assert upd.status_code == 200
    assert upd.json()["enabled"] is False

    # Delete
    dele = client.delete(f"/api/v1/important-routes/{created['id']}")
    assert dele.status_code == 204


def test_feature1_end_to_end_change_workflow(client: TestClient):
    # 1. Sync from Mock ServiceNow
    sync_resp = client.post("/api/v1/changes/sync")
    assert sync_resp.status_code == 200
    assert sync_resp.json()["synced_count"] >= 2

    changes = client.get("/api/v1/changes").json()
    target = next(c for c in changes if c["chg_number"] == "CHG0042108")
    change_id = target["id"]

    # Post-capture before pre-capture must be rejected cleanly
    premature = client.post(f"/api/v1/changes/{change_id}/trigger-post-capture")
    assert premature.status_code == 400

    # 2. Trigger pre-change capture (collects EdgeConnect + Cisco Nexus concurrently)
    pre_resp = client.post(f"/api/v1/changes/{change_id}/trigger-pre-capture")
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
    assert set(pre_data["succeeded_devices"]) == {"uec-abc-prd01", "nx-dc1-core01"}
    assert pre_data["failed_devices"] == []

    # 3. Trigger post-change capture & parallel comparison
    post_resp = client.post(f"/api/v1/changes/{change_id}/trigger-post-capture")
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert len(post_data["reports_generated"]) == 2

    # 4. Inspect change detail & email preview
    detail = client.get(f"/api/v1/changes/{change_id}").json()
    assert detail["status"] == "completed"
    assert len(detail["reports"]) == 2

    ec_report = next(r for r in detail["reports"] if r["device_label"] == "uec-abc-prd01")
    assert ec_report["risk_level"] == "CRITICAL"
    assert ec_report["summary_stats"]["removed_count"] == 10
    assert ec_report["summary_stats"]["important_count"] == 7

    preview = client.get(f"/api/v1/reports/{ec_report['id']}/email-preview")
    assert preview.status_code == 200
    assert "CHG0042108" in preview.json()["subject"]
    assert "10.132.0.0/14" in preview.json()["html"]
    assert "route-comparison-CHG0042108.csv" in preview.json()["html"]

    csv_resp = client.get(f"/api/v1/reports/{ec_report['id']}/export-csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "attachment; filename=" in csv_resp.headers["content-disposition"]
    csv_lines = csv_resp.content.decode("utf-8-sig").strip().splitlines()
    # 1 header + 49 expanded route-entry diff rows (40 removed entries + 9 added entries; net -31)
    assert len(csv_lines) == 50
    assert "10.132.0.0/14" in csv_resp.text


def test_delete_completed_change_request_and_reject_active_changes(client: TestClient):
    # Sync initial mock ServiceNow changes
    assert client.post("/api/v1/changes/sync").status_code == 200
    changes = client.get("/api/v1/changes").json()
    target = next(c for c in changes if c["chg_number"] == "CHG0042108")
    change_id = target["id"]

    # Non-existent change returns 404
    assert client.delete("/api/v1/changes/999999").status_code == 404

    # Deleting a synced (not completed) change is rejected with 400
    bad_synced = client.delete(f"/api/v1/changes/{change_id}")
    assert bad_synced.status_code == 400
    assert "Only completed change requests can be deleted" in bad_synced.json()["detail"]

    # Pre-captured (still not completed) change is also rejected with 400
    assert client.post(f"/api/v1/changes/{change_id}/trigger-pre-capture").status_code == 200
    bad_pre = client.delete(f"/api/v1/changes/{change_id}")
    assert bad_pre.status_code == 400

    # Complete the change via post-capture & comparison
    post_resp = client.post(f"/api/v1/changes/{change_id}/trigger-post-capture")
    assert post_resp.status_code == 200
    report_ids = [r["id"] for r in post_resp.json()["reports_generated"]]
    assert len(report_ids) == 2

    # Delete the completed change request -> 204
    del_resp = client.delete(f"/api/v1/changes/{change_id}")
    assert del_resp.status_code == 204

    # Change and its linked reports are gone
    assert client.get(f"/api/v1/changes/{change_id}").status_code == 404
    for rep_id in report_ids:
        assert client.get(f"/api/v1/reports/{rep_id}").status_code == 404

    # Subsequent ServiceNow sync must NOT resurrect the deleted completed change
    assert client.post("/api/v1/changes/sync").status_code == 200
    remaining = client.get("/api/v1/changes").json()
    assert all(c["chg_number"] != "CHG0042108" for c in remaining)


def test_adhoc_demo_csv_and_file_upload_comparison(client: TestClient, sample_data_dir: Path):
    demo_resp = client.post("/api/v1/comparisons/demo-csv")
    assert demo_resp.status_code == 200
    assert demo_resp.json()["summary_stats"]["total_differences"] == 14

    before_bytes = (sample_data_dir / "subnetsExample_beforeChange.csv").read_bytes()
    after_bytes = (sample_data_dir / "subnetsExample_afterChange.csv").read_bytes()
    upload_resp = client.post(
        "/api/v1/comparisons/adhoc",
        data={"device_label": "uploaded-ec-01"},
        files={
            "before_file": ("before.csv", before_bytes, "text/csv"),
            "after_file": ("after.csv", after_bytes, "text/csv"),
        },
    )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["device_label"] == "uploaded-ec-01"
    assert upload_resp.json()["summary_stats"]["important_count"] == 7

    # Remote sample CSV download endpoints for independent verification
    dl_before = client.get("/api/v1/sample-data/before")
    assert dl_before.status_code == 200
    assert "subnetsExample_beforeChange.csv" in dl_before.headers["content-disposition"]
    assert dl_before.content == before_bytes

    dl_after = client.get("/api/v1/sample-data/after")
    assert dl_after.status_code == 200
    assert "subnetsExample_afterChange.csv" in dl_after.headers["content-disposition"]
    assert dl_after.content == after_bytes

    assert client.get("/api/v1/sample-data/invalid").status_code == 400


def test_feature2_route_summary_by_device_ip_hostname_text_and_demo(client: TestClient):
    # Query by hostname (EdgeConnect)
    resp_host = client.post("/api/v1/route-summary/device", json={"query": "uec-abc-prd01"})
    assert resp_host.status_code == 200
    data = resp_host.json()
    assert data["output_route_count"] == 175
    assert data["summary_route_count"] == 27
    assert data["remaining_route_count"] == 148
    assert data["ignored_default_routes"] == 15

    # Query by IP address (Cisco Nexus)
    resp_ip = client.post("/api/v1/route-summary/device", json={"query": "10.0.1.11"})
    assert resp_ip.status_code == 200
    assert resp_ip.json()["device_type"] == "cisco_nexus"
    assert resp_ip.json()["summary_route_count"] == 2

    # Unknown device returns 404
    missing = client.post("/api/v1/route-summary/device", json={"query": "192.0.2.99"})
    assert missing.status_code == 404

    # Plain CIDR mini-example via text endpoint
    text_resp = client.post(
        "/api/v1/route-summary/text",
        json={
            "source_label": "Mini Test",
            "raw_text": (
                "10.1.0.0/16\n10.1.1.0/24\n10.1.5.0/25\n"
                "10.2.2.0/26\n172.16.2.0/24\n172.16.2.128/26\n192.168.8.0/26"
            ),
        },
    )
    assert text_resp.status_code == 200
    assert [r["prefix"] for r in text_resp.json()["all_output_routes"]] == [
        "10.1.0.0/16",
        "10.2.2.0/26",
        "172.16.2.0/24",
        "192.168.8.0/26",
    ]

    # Demo CSV endpoint
    demo_resp = client.post("/api/v1/route-summary/demo-csv?include_supernet_suggestions=true")
    assert demo_resp.status_code == 200
    assert demo_resp.json()["output_route_count"] == 175


def test_mock_servicenow_simulator_and_settings_endpoints(client: TestClient):
    devices = client.get("/api/v1/devices").json()
    create_resp = client.post(
        "/api/v1/mock-servicenow/changes",
        json={
            "chg_number": "CHG0088801",
            "title": "API Simulated Change",
            "scheduled_start": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "engineer_name": "Sam Lee",
            "engineer_email": "sam.lee@netops.local",
            "ci_device_ids": [devices[0]["id"]],
        },
    )
    assert create_resp.status_code == 201

    changes = client.get("/api/v1/changes").json()
    assert any(c["chg_number"] == "CHG0088801" for c in changes)

    # Update settings
    upd = client.put("/api/v1/settings", json={"large_prefix_threshold": 19})
    assert upd.status_code == 200
    assert upd.json()["large_prefix_threshold"] == 19

    # Scheduler status endpoint
    sched = client.get("/api/v1/scheduler/status")
    assert sched.status_code == 200
    assert sched.json()["synced_changes_count"] >= 1
