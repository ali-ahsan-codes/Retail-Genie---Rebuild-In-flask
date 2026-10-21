"""Private cloud-file pages and tenant-authorized APIs."""

from pathlib import Path

from flask import abort, current_app, jsonify, render_template, request, send_file
from flask_login import current_user, login_required

from ..extensions import db
from . import cloud_bp
from .service import (
    CloudRuleError,
    authorized_file_path,
    delete_file,
    file_dict,
    list_files,
    share_file,
    unshare_file,
    update_file_notes,
    upload_file,
)


def _payload() -> dict:
    if request.is_json:
        value = request.get_json(silent=True)
        return value if isinstance(value, dict) else {}
    return request.form.to_dict(flat=True)


def _error(error: CloudRuleError):
    return jsonify(error=error.code, message=str(error)), error.status_code


@cloud_bp.get("/my-cloud")
@login_required
def my_cloud_page():
    try:
        files = list_files(current_user, search=request.args.get("q"))
    except CloudRuleError as error:
        abort(error.status_code)
    return render_template("cloud/index.html", files=files, search=request.args.get("q", ""))


@cloud_bp.get("/admin/file-management")
@login_required
def file_management_page():
    if not current_user.has_permission("manage_cloud_files"):
        abort(403)
    try:
        files = list_files(current_user, search=request.args.get("q"))
    except CloudRuleError as error:
        abort(error.status_code)
    return render_template("cloud/index.html", files=files, search=request.args.get("q", ""), is_admin=True)


@cloud_bp.get("/api/v1/cloud/files")
@login_required
def list_files_api():
    try:
        files = list_files(current_user, search=request.args.get("q"))
    except CloudRuleError as error:
        return _error(error)
    return jsonify({"files": files}), 200


@cloud_bp.post("/api/v1/cloud/files")
@login_required
def upload_file_api():
    data = _payload()
    row = None
    try:
        row = upload_file(current_user, file_storage=request.files.get("file"), notes=data.get("notes"))
        db.session.commit()
    except CloudRuleError as error:
        db.session.rollback()
        if row is not None:
            path = Path(current_app.config["UPLOADS_DIR"]).resolve() / row.file_path
            if path.is_file():
                path.unlink()
        return _error(error)
    except Exception:
        db.session.rollback()
        if row is not None:
            path = Path(current_app.config["UPLOADS_DIR"]).resolve() / row.file_path
            if path.is_file():
                path.unlink()
        raise
    return jsonify({"file": file_dict(row)}), 201


@cloud_bp.get("/api/v1/cloud/files/<string:file_id>")
@login_required
def download_file_api(file_id: str):
    try:
        row, path = authorized_file_path(current_user, file_id)
    except CloudRuleError as error:
        return _error(error)
    response = send_file(
        path,
        mimetype=row.mime_type or "application/octet-stream",
        as_attachment=True,
        download_name=row.original_name,
        conditional=True,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@cloud_bp.patch("/api/v1/cloud/files/<string:file_id>/notes")
@login_required
def update_notes_api(file_id: str):
    data = _payload()
    try:
        row = update_file_notes(current_user, file_id=file_id, notes=data.get("notes"))
        db.session.commit()
    except CloudRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"file": file_dict(row)}), 200


@cloud_bp.delete("/api/v1/cloud/files/<string:file_id>")
@login_required
def delete_file_api(file_id: str):
    try:
        path = delete_file(current_user, file_id=file_id)
        db.session.commit()
    except CloudRuleError as error:
        db.session.rollback()
        return _error(error)
    if path.is_file():
        path.unlink()
    return jsonify({"deleted": True}), 200


@cloud_bp.post("/api/v1/cloud/files/<string:file_id>/share")
@login_required
def share_file_api(file_id: str):
    data = _payload()
    users = data.get("user_ids") or []
    if isinstance(users, str):
        users = [users]
    try:
        row = share_file(
            current_user,
            file_id=file_id,
            scope=str(data.get("scope", "user")),
            unit_id=data.get("unit_id") or None,
            user_ids=[str(value) for value in users],
        )
        db.session.commit()
    except CloudRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"file": file_dict(row)}), 200


@cloud_bp.post("/api/v1/cloud/files/<string:file_id>/unshare")
@login_required
def unshare_file_api(file_id: str):
    data = _payload()
    try:
        row = unshare_file(current_user, file_id=file_id, user_id=data.get("user_id") or None)
        db.session.commit()
    except CloudRuleError as error:
        db.session.rollback()
        return _error(error)
    return jsonify({"file": file_dict(row)}), 200
