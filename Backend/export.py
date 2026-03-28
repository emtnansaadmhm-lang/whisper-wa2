from flask import Blueprint, request, send_file, jsonify
import csv
import io
import os
from datetime import datetime

from reports import append_report, REPORTS_DIR

bp_export = Blueprint("bp_export", __name__)

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def build_report_meta(body, file_name, file_path, file_type):
    now = datetime.now()

    return {
        "id": int(now.timestamp() * 1000),
        "investigator": body.get("investigator", "Unknown"),
        "date": body.get("date") or now.strftime("%Y-%m-%d"),
        "time": body.get("time") or now.strftime("%H:%M"),
        "caseNumber": body.get("caseNumber", "---"),
        "deviceInfo": body.get("deviceInfo", "---"),
        "status": body.get("status", "completed"),
        "fileName": file_name,
        "filePath": file_path,
        "fileType": file_type,
    }


# ================= CSV =================
@bp_export.route("/api/export/csv", methods=["POST"])
def export_csv():
    body = request.get_json(silent=True) or {}
    data = body.get("messages", [])

    if not data:
        return jsonify({"error": "No data provided"}), 400

    report_id = int(datetime.now().timestamp() * 1000)
    case_number = body.get("caseNumber", "CASE")
    safe_case = str(case_number).replace("/", "_").replace("\\", "_").replace(" ", "_")

    file_name = f"forensic_report_{safe_case}_{report_id}.csv"
    file_path = os.path.join(REPORTS_DIR, file_name)

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Message", "Type", "Number", "DateTime"])

        for msg in data:
            writer.writerow([
                msg.get("message", ""),
                msg.get("type", ""),
                msg.get("number", ""),
                msg.get("datetime", "")
            ])

    report = build_report_meta(body, file_name, file_path, "csv")
    report["id"] = report_id
    append_report(report)

    return send_file(
        file_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=file_name
    )


# ================= PDF =================
@bp_export.route("/api/export/pdf", methods=["POST"])
def export_pdf():
    if not REPORTLAB_AVAILABLE:
        return jsonify({
            "error": "PDF export is not available because reportlab is not installed"
        }), 500

    body = request.get_json(silent=True) or {}
    data = body.get("messages", [])

    if not data:
        return jsonify({"error": "No data provided"}), 400

    report_id = int(datetime.now().timestamp() * 1000)
    case_number = body.get("caseNumber", "CASE")
    safe_case = str(case_number).replace("/", "_").replace("\\", "_").replace(" ", "_")

    file_name = f"forensic_report_{safe_case}_{report_id}.pdf"
    file_path = os.path.join(REPORTS_DIR, file_name)

    pdf = canvas.Canvas(file_path, pagesize=letter)
    y = 750
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Whisper-WA Forensic Report")
    y -= 25

    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, y, f"Case Number: {body.get('caseNumber', '---')}")
    y -= 18
    pdf.drawString(50, y, f"Investigator: {body.get('investigator', 'Unknown')}")
    y -= 18
    pdf.drawString(50, y, f"Device: {body.get('deviceInfo', '---')}")
    y -= 30

    for msg in data:
        line = f"{msg.get('datetime', '')} | {msg.get('number', '')} | {msg.get('type', '')} | {msg.get('message', '')}"
        if len(line) > 120:
            line = line[:117] + "..."

        pdf.drawString(50, y, line)
        y -= 18

        if y < 50:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 750

    pdf.save()

    report = build_report_meta(body, file_name, file_path, "pdf")
    report["id"] = report_id
    append_report(report)

    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_name,
        mimetype="application/pdf"
    )