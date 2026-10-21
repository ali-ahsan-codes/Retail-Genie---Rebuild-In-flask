import io

from retail_genie.extensions import db
from retail_genie.models import CloudFile


def test_private_cloud_upload_is_tenant_scoped_and_delete_is_consistent(app, client, create_user, tmp_path):
    app.config["UPLOADS_DIR"] = str(tmp_path / "private-uploads")
    create_user("cloud.owner", role="salesperson", permissions=["upload_cloud"])
    create_user("cloud.other", role="salesperson", permissions=[])
    client.post("/login", data={"username": "cloud.owner", "password": "A-long-test-password-4!"})
    page = client.get("/my-cloud")
    nonce = page.headers["Content-Security-Policy"].split("script-src 'self' 'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"'.encode() in page.data
    uploaded = client.post("/api/v1/cloud/files", data={"notes": "delivery evidence", "file": (io.BytesIO(b"private report"), "report.txt")}, content_type="multipart/form-data")
    assert uploaded.status_code == 201, uploaded.get_json()
    file_data = uploaded.get_json()["file"]
    listed = client.get("/api/v1/cloud/files")
    assert listed.status_code == 200 and len(listed.get_json()["files"]) == 1
    download = client.get(f"/api/v1/cloud/files/{file_data['id']}")
    assert download.status_code == 200
    assert download.data == b"private report"
    client.post("/logout")
    client.post("/login", data={"username": "cloud.other", "password": "A-long-test-password-4!"})
    denied = client.get(f"/api/v1/cloud/files/{file_data['id']}")
    assert denied.status_code == 403
    client.post("/logout")
    client.post("/login", data={"username": "cloud.owner", "password": "A-long-test-password-4!"})
    with app.app_context():
        row = db.session.get(CloudFile, file_data["id"])
        path = tmp_path / "private-uploads" / row.file_path
        assert path.is_file()
    deleted = client.delete(f"/api/v1/cloud/files/{file_data['id']}")
    assert deleted.status_code == 200
    with app.app_context():
        assert db.session.get(CloudFile, file_data["id"]) is None
        assert not path.exists()
