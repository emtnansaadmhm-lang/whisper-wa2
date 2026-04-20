import os
import sqlite3
from flask import Blueprint, jsonify
from parser import parse_whatsapp_db
from analysis import analyze_whatsapp_data

bp_analysis = Blueprint("bp_analysis", __name__)



def get_owner_number_from_db(case_id):
    """استخراج رقم صاحب الحساب من قاعدة بيانات wa.db"""
    # مسار قاعدة البيانات داخل مجلد القضية المستخرجة
    db_path = os.path.join("Cases", case_id, "extracted", "wa.db")
    
    if not os.path.exists(db_path):
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # الاستعلام عن الرقم الذي يمثل صاحب الحساب (me)
        # ملاحظة: jid في جدول wa_contacts غالباً ما يحتوي على رقم صاحب الجهاز
        cursor.execute("SELECT jid FROM wa_contacts WHERE is_whatsapp_user = 1 AND jid LIKE '%@s.whatsapp.net' LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # تنظيف الرقم من @s.whatsapp.net
            number = row[0].split('@')[0]
            return f"+{number}"
    except Exception as e:
        print(f"Error fetching owner number: {e}")
    return None

@bp_analysis.route("/api/case-info/<case_id>")
def api_get_case_info(case_id):
    """نقطة نهاية جديدة لتعطينا معلومات القضية شاملة رقم الهاتف"""
    owner_num = get_owner_number_from_db(case_id)
    return jsonify({
        "ok": True,
        "case_id": case_id,
        "owner_number": owner_num or "Unknown Number"
    })



@bp_analysis.route("/api/analysis/<case_id>", methods=["GET"])
def get_case_analysis(case_id):
    try:
        parsed = parse_whatsapp_db(case_id)

        if not parsed.get("ok"):
            return jsonify({
                "ok": False,
                "error": parsed.get("error", "Failed to parse database")
            }), 400

        messages = parsed.get("messages", [])

        if not messages:
            return jsonify({
                "ok": False,
                "error": "No messages found for analysis"
            }), 200

        analysis_result = analyze_whatsapp_data(messages, case_id)

        if not isinstance(analysis_result, dict):
            return jsonify({
                "ok": False,
                "error": "Analysis returned invalid format"
            }), 500

        if not analysis_result.get("ok"):
            return jsonify({
                "ok": False,
                "error": analysis_result.get("error", "Analysis failed")
            }), 400

        # لا تحفظ ملف هنا عشان ما يصير لوب إعادة تحميل
        analysis_result["report_path"] = None

        return jsonify(analysis_result), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
