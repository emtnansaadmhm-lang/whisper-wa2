from flask import Blueprint, request, send_file, jsonify
import csv
import os
from datetime import datetime

from reports import append_report, REPORTS_DIR

bp_export = Blueprint("bp_export", __name__)

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_AVAILABLE = True
except ImportError:
    ARABIC_AVAILABLE = False


def fix_arabic(text):
    text = str(text) if text is not None else ""

    if not ARABIC_AVAILABLE:
        return text

    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def register_arabic_font():
    font_paths = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for path in font_paths:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("ArabicFont", path))
            return "ArabicFont"

    return "Helvetica"


def safe_text(text, max_len=120):
    text = str(text) if text is not None else ""
    text = text.replace("\n", " ").replace("\r", " ")

    if len(text) > max_len:
        text = text[:max_len - 3] + "..."

    return fix_arabic(text)


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

    font_name = register_arabic_font()

    pdf = canvas.Canvas(file_path, pagesize=letter)

    page_width, page_height = letter
    right_x = page_width - 50
    y = 750

    # ===== Title =====
    pdf.setFont(font_name, 14)
    pdf.drawRightString(right_x, y, safe_text("Whisper-WA Forensic Report"))
    y -= 30

    # ===== Info =====
    pdf.setFont(font_name, 10)

    pdf.drawRightString(
        right_x,
        y,
        safe_text(f"Case Number: {body.get('caseNumber', '---')}")
    )
    y -= 18

    pdf.drawRightString(
        right_x,
        y,
        safe_text(f"Investigator: {body.get('investigator', 'Unknown')}")
    )
    y -= 30

    # ===== Evidence Section =====
    pdf.drawRightString(
        right_x,
        y,
        safe_text("Evidence of Interest:")
    )
    y -= 18

    pdf.drawRightString(
        right_x,
        y,
        safe_text("The following extracted messages are considered relevant to the forensic investigation.")
    )
    y -= 30

    # ===== Messages =====
    pdf.drawRightString(right_x, y, safe_text("Extracted Messages:"))
    y -= 22

    for msg in data:
        line = (
            f"{msg.get('datetime', '')} | "
            f"{msg.get('number', '')} | "
            f"{msg.get('type', '')} | "
            f"{msg.get('message', '')}"
        )

        pdf.drawRightString(right_x, y, safe_text(line, 115))
        y -= 18

        if y < 50:
            pdf.showPage()
            pdf.setFont(font_name, 10)
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
