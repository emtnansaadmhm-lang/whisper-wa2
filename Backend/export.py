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


def safe_text(text, max_len=120, arabic=True):
    text = str(text) if text is not None else ""
    text = text.replace("\n", " ").replace("\r", " ")

    if len(text) > max_len:
        text = text[:max_len - 3] + "..."

    return fix_arabic(text) if arabic else text


def get_message_label(msg):
    text = msg.get("message", "")
    media_type = msg.get("media_type", "")

    if text:
        return text

    if media_type == "image":
        return "[Image Evidence]"

    if media_type:
        return f"[{media_type} Evidence]"

    return "Media / Attachment"


def resolve_media_path(media_url):
    if not media_url:
        return None

    clean = str(media_url).strip()
    base_dir = os.path.dirname(os.path.abspath(__file__))

    if clean.startswith("http://") or clean.startswith("https://"):
        return None

    stripped = clean.lstrip("/")

    if stripped.startswith("api/media/"):
        stripped = stripped.replace("api/media/", "", 1)

    if stripped.startswith("media/"):
        stripped = stripped.replace("media/", "", 1)

    parts = stripped.split("/", 1)

    candidates = [
        clean,
        clean.lstrip("/"),
        os.path.join(base_dir, clean.lstrip("/")),
    ]

    if len(parts) == 2:
        case_id, media_subpath = parts
        candidates.extend([
            os.path.join(base_dir, "Cases", case_id, "Evidence", "Media", media_subpath),
            os.path.join(base_dir, "Cases", case_id, "Evidence", "Media", "Media", media_subpath),
            os.path.join(base_dir, "Cases", case_id, "Evidence", media_subpath),
            os.path.join(base_dir, "Cases", case_id, media_subpath),
        ])

    for path in candidates:
        if path and os.path.exists(path):
            return path

    return None


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


def draw_centered_title(pdf, text, y, font_name, size=22):
    page_width, _ = letter
    pdf.setFont(font_name, size)
    pdf.setFillColorRGB(0.03, 0.16, 0.32)
    pdf.drawCentredString(page_width / 2, y, safe_text(text, arabic=False))


def draw_section_label(pdf, text, y, font_name):
    page_width, _ = letter
    label_w = 190
    label_h = 24
    x = (page_width - label_w) / 2

    pdf.setFillColorRGB(0.03, 0.16, 0.32)
    pdf.roundRect(x, y - 6, label_w, label_h, 4, fill=1, stroke=0)

    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont(font_name, 11)
    pdf.drawCentredString(page_width / 2, y, safe_text(text, arabic=False))


def draw_footer(pdf, font_name):
    page_width, _ = letter
    pdf.setStrokeColorRGB(0.70, 0.76, 0.84)
    pdf.line(55, 58, page_width - 55, 58)

    pdf.setFillColorRGB(0.25, 0.25, 0.25)
    pdf.setFont(font_name, 8)
    pdf.drawCentredString(
        page_width / 2,
        42,
        safe_text(f"Report generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", arabic=False)
    )

    pdf.setFont(font_name, 8)
    pdf.drawCentredString(
        page_width / 2,
        28,
        safe_text("Confidential forensic report - authorized personnel only.", arabic=False)
    )


def draw_page_header(pdf, font_name):
    page_width, page_height = letter

    pdf.setFillColorRGB(0.03, 0.16, 0.32)
    pdf.rect(0, page_height - 20, page_width, 20, fill=1, stroke=0)

    pdf.setStrokeColorRGB(0.03, 0.16, 0.32)
    pdf.setLineWidth(1.2)
    pdf.line(70, 680, page_width - 70, 680)

    draw_centered_title(pdf, "WHISPER-WA FORENSIC REPORT", 700, font_name, 21)


def new_page(pdf, font_name):
    pdf.showPage()
    draw_page_header(pdf, font_name)
    draw_footer(pdf, font_name)
    return 635


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
        writer.writerow(["Message", "Type", "Number", "DateTime", "Media Type", "Media URL", "Media Name"])

        for msg in data:
            writer.writerow([
                get_message_label(msg),
                msg.get("type", ""),
                msg.get("number", ""),
                msg.get("datetime", ""),
                msg.get("media_type", ""),
                msg.get("media_url", ""),
                msg.get("media_name", "")
            ])

    report = build_report_meta(body, file_name, file_path, "csv")
    report["id"] = report_id
    append_report(report)

    return send_file(file_path, mimetype="text/csv", as_attachment=True, download_name=file_name)


# ================= PDF =================
@bp_export.route("/api/export/pdf", methods=["POST"])
def export_pdf():
    if not REPORTLAB_AVAILABLE:
        return jsonify({"error": "PDF export is not available because reportlab is not installed"}), 500

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

    draw_page_header(pdf, font_name)
    draw_footer(pdf, font_name)

    # Case info box
    box_x = 95
    box_y = 610
    box_w = page_width - 190
    box_h = 58

    pdf.setStrokeColorRGB(0.80, 0.84, 0.90)
    pdf.setFillColorRGB(0.98, 0.99, 1)
    pdf.roundRect(box_x, box_y, box_w, box_h, 5, fill=1, stroke=1)

    pdf.setFillColorRGB(0.03, 0.16, 0.32)
    pdf.setFont(font_name, 10)
    pdf.drawString(box_x + 35, box_y + 35, safe_text("Case Number:", arabic=False))
    pdf.drawString(box_x + 35, box_y + 17, safe_text(str(body.get("caseNumber", "---")), arabic=False))

    pdf.line(page_width / 2, box_y + 12, page_width / 2, box_y + box_h - 12)

    pdf.drawString(page_width / 2 + 35, box_y + 35, safe_text("Investigator:", arabic=False))
    pdf.drawString(page_width / 2 + 35, box_y + 17, safe_text(str(body.get("investigator", "Unknown")), arabic=False))

    y = 555

    draw_section_label(pdf, "EVIDENCE OF INTEREST", y, font_name)
    y -= 48

    pdf.setStrokeColorRGB(0.80, 0.84, 0.90)
    pdf.setFillColorRGB(0.98, 0.99, 1)
    pdf.roundRect(80, y - 15, page_width - 160, 45, 5, fill=1, stroke=1)

    pdf.setFillColorRGB(0.12, 0.12, 0.12)
    pdf.setFont(font_name, 10)
    pdf.drawCentredString(
        page_width / 2,
        y + 2,
        safe_text("The following extracted messages are considered relevant to the forensic investigation.", arabic=False)
    )

    y -= 70
    draw_section_label(pdf, "EXTRACTED MESSAGES", y, font_name)
    y -= 40

    # Table
    left = 55
    table_w = page_width - 110
    row_h = 32

    col_date = 145
    col_number = 125
    col_type = 105
    col_message = table_w - col_date - col_number - col_type

    def draw_table_header(y_pos):
        pdf.setFillColorRGB(0.03, 0.16, 0.32)
        pdf.roundRect(left, y_pos - row_h, table_w, row_h, 4, fill=1, stroke=0)

        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont(font_name, 9)
        pdf.drawCentredString(left + col_date / 2, y_pos - 20, "DATE & TIME")
        pdf.drawCentredString(left + col_date + col_number / 2, y_pos - 20, "PHONE NUMBER")
        pdf.drawCentredString(left + col_date + col_number + col_type / 2, y_pos - 20, "DIRECTION")
        pdf.drawCentredString(left + col_date + col_number + col_type + col_message / 2, y_pos - 20, "MESSAGE PREVIEW")

        return y_pos - row_h

    y = draw_table_header(y)

    for msg in data:
        if y < 100:
            y = new_page(pdf, font_name)
            y = draw_table_header(y)

        message_label = get_message_label(msg)
        media_url = msg.get("media_url", "")
        media_type = msg.get("media_type", "")

        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(left, y - row_h, table_w, row_h, fill=1, stroke=0)

        pdf.setStrokeColorRGB(0.86, 0.89, 0.93)
        pdf.rect(left, y - row_h, table_w, row_h, fill=0, stroke=1)

        pdf.setFillColorRGB(0.10, 0.10, 0.10)
        pdf.setFont(font_name, 8.5)

        pdf.drawCentredString(left + col_date / 2, y - 20, safe_text(msg.get("datetime", ""), 25, arabic=False))
        pdf.drawCentredString(left + col_date + col_number / 2, y - 20, safe_text(msg.get("number", ""), 25, arabic=False))
        pdf.drawCentredString(left + col_date + col_number + col_type / 2, y - 20, safe_text(msg.get("type", ""), 18, arabic=False))

        # الرسالة فقط هنا، مو Name
        msg_x = left + col_date + col_number + col_type + col_message / 2
        pdf.drawCentredString(msg_x, y - 20, safe_text(message_label, 45, arabic=True))

        y -= row_h

        if media_url and media_type == "image":
            try:
                img_path = resolve_media_path(media_url)

                if img_path and os.path.exists(img_path):
                    if y < 190:
                        y = new_page(pdf, font_name)

                    pdf.setFont(font_name, 9)
                    pdf.setFillColorRGB(0.03, 0.16, 0.32)
                    pdf.drawString(left, y - 18, safe_text("Attached Image Evidence:", arabic=False))

                    pdf.drawImage(
                        img_path,
                        left,
                        y - 145,
                        width=120,
                        height=120,
                        preserveAspectRatio=True
                    )
                    y -= 155
                else:
                    pdf.setFont(font_name, 8)
                    pdf.setFillColorRGB(0.55, 0.10, 0.10)
                    pdf.drawString(left, y - 16, safe_text(f"Image path not found: {media_url}", 90, arabic=False))
                    y -= 25

            except Exception as e:
                print("Image load error:", e)
                pdf.setFont(font_name, 8)
                pdf.drawString(left, y - 16, safe_text("Image could not be embedded in PDF.", arabic=False))
                y -= 25

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