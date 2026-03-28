import json
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file

bp_reports = Blueprint("bp_reports", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_FILE = os.path.join(BASE_DIR, "reports_db.json")
REPORTS_DIR = os.path.join(BASE_DIR, "saved_reports")

os.makedirs(REPORTS_DIR, exist_ok=True)

def load_reports():
    if not os.path.exists(REPORTS_FILE):
        return []
    try:
        with open(REPORTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_reports(data):
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def append_report(report):
    reports = load_reports()
    reports.append(report)
    save_reports(reports)
    return report

@bp_reports.route("/api/reports", methods=["GET"])
def get_reports():
    reports = load_reports()
    investigator = request.args.get("investigator")
    role = request.args.get("role", "user")

    if role != "admin" and investigator:
        reports = [r for r in reports if r.get("investigator") == investigator]

    reports = sorted(reports, key=lambda x: x.get("id", 0), reverse=True)
    return jsonify({"ok": True, "reports": reports})

@bp_reports.route("/api/reports", methods=["POST"])
def create_report():
    body = request.get_json(silent=True) or {}
    now = datetime.now()

    report = {
        "id": int(now.timestamp() * 1000),
        "investigator": body.get("investigator", "Unknown"),
        "date": body.get("date") or now.strftime("%Y-%m-%d"),
        "time": body.get("time") or now.strftime("%H:%M"),
        "caseNumber": body.get("caseNumber", "---"),
        "deviceInfo": body.get("deviceInfo", "---"),
        "status": body.get("status", "completed"),
        "fileName": body.get("fileName", ""),
        "filePath": body.get("filePath", ""),
        "fileType": body.get("fileType", ""),
    }

    append_report(report)
    return jsonify({"ok": True, "report": report}), 201

@bp_reports.route("/api/reports/<int:report_id>", methods=["DELETE"])
def delete_report(report_id):
    reports = load_reports()
    target = next((r for r in reports if r.get("id") == report_id), None)

    if not target:
        return jsonify({"ok": False, "error": "Not found"}), 404

    file_path = target.get("filePath")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    updated = [r for r in reports if r.get("id") != report_id]
    save_reports(updated)
    return jsonify({"ok": True})

@bp_reports.route("/api/reports/<int:report_id>/status", methods=["PATCH"])
def update_status(report_id):
    body = request.get_json(silent=True) or {}
    new_status = body.get("status")

    if new_status not in ("completed", "pending", "archived"):
        return jsonify({"ok": False, "error": "Invalid status"}), 400

    reports = load_reports()
    for r in reports:
        if r.get("id") == report_id:
            r["status"] = new_status
            save_reports(reports)
            return jsonify({"ok": True, "report": r})

    return jsonify({"ok": False, "error": "Not found"}), 404

@bp_reports.route("/api/reports/<int:report_id>/download", methods=["GET"])
def download_report(report_id):
    reports = load_reports()
    report = next((r for r in reports if r.get("id") == report_id), None)

    if not report:
        return jsonify({"ok": False, "error": "Report not found"}), 404

    file_path = report.get("filePath")
    file_name = report.get("fileName") or f"report_{report_id}"

    if not file_path or not os.path.exists(file_path):
        return jsonify({"ok": False, "error": "File not found"}), 404

    return send_file(file_path, as_attachment=True, download_name=file_name)