from retail_genie.extensions import db
from retail_genie.models import AuditEvent, AttendanceLog, BreakLog


def test_attendance_and_break_transitions_are_tenant_scoped_and_audited(app, client, create_user):
    create_user("attendance.staff", role="salesperson", permissions=[])
    create_user("attendance.manager", role="manager", permissions=["view_reports"])
    client.post("/login", data={"username": "attendance.staff", "password": "A-long-test-password-4!"})
    assert client.get("/attendance").status_code == 200
    clocked_in = client.post("/api/v1/attendance/clock-in", json={"method": "manual"})
    assert clocked_in.status_code == 201, clocked_in.get_json()
    duplicate = client.post("/api/v1/attendance/clock-in", json={"method": "manual"})
    assert duplicate.status_code == 409
    started = client.post("/api/v1/breaks", json={})
    assert started.status_code == 201, started.get_json()
    break_id = started.get_json()["break"]["id"]
    ended = client.post(f"/api/v1/breaks/{break_id}/end", json={})
    assert ended.status_code == 200, ended.get_json()
    clocked_out = client.post("/api/v1/attendance/clock-out", json={})
    assert clocked_out.status_code == 200
    with app.app_context():
        assert AttendanceLog.query.count() == 1
        assert BreakLog.query.one().is_active is False
        assert AuditEvent.query.filter(AuditEvent.action.in_(["attendance.clocked_in", "attendance.clocked_out", "attendance.break_started", "attendance.break_ended"])).count() == 4
    client.post("/logout")
    client.post("/login", data={"username": "attendance.manager", "password": "A-long-test-password-4!"})
    assert client.get("/admin/breaks-dashboard").status_code == 200


def test_attendance_selfie_is_private_and_only_visible_to_owner(app, client, create_user, tmp_path):
    app.config["UPLOADS_DIR"] = str(tmp_path / "private-media")
    create_user("selfie.owner", role="salesperson", permissions=[])
    create_user("selfie.other", role="salesperson", permissions=[])
    client.post("/login", data={"username": "selfie.owner", "password": "A-long-test-password-4!"})
    image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pV0AAAAASUVORK5CYII="
    response = client.post("/api/v1/attendance/clock-in", json={"method": "selfie", "selfie_data_uri": image})
    assert response.status_code == 201, response.get_json()
    log_id = response.get_json()["attendance"]["id"]
    selfie = client.get(f"/api/v1/attendance/logs/{log_id}/selfie")
    assert selfie.status_code == 200 and selfie.mimetype == "image/png"
    assert "no-store" in selfie.headers["Cache-Control"]
    client.post("/logout")
    client.post("/login", data={"username": "selfie.other", "password": "A-long-test-password-4!"})
    denied = client.get(f"/api/v1/attendance/logs/{log_id}/selfie")
    assert denied.status_code == 403
