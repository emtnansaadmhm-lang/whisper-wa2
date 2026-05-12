from flask import Blueprint, jsonify
from parser import parse_whatsapp_db
from analysis import analyze_whatsapp_data

bp_analysis = Blueprint("bp_analysis", __name__)

# Cache لمنع إعادة التحليل كل ثانية
analysis_cache = {}

@bp_analysis.route("/api/analysis/<case_id>", methods=["GET"])
def get_case_analysis(case_id):
    try:

        # إذا التحليل موجود بالكاش رجعه مباشرة
        if case_id in analysis_cache:
            return jsonify(analysis_cache[case_id]), 200

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

        # خزّن النتيجة
        analysis_cache[case_id] = analysis_result

        return jsonify(analysis_result), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
