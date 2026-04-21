from flask import Blueprint, jsonify
from database import get_all_cases
bp_cases = Blueprint("bp_cases", __name__)
@bp_cases.route("/api/cases", methods=["GET"])
def api_get_cases():
    cases = get_all_cases()
    cases = sorted(
        cases,
        key=lambda c: c.created_at or "",
        reverse=True
    )
    return jsonify({
        "ok": True,
        "cases": [
            {
                "id": c.id,
                "case_id": c.case_name,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "created_at_text": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "No date"
            }
            for c in cases
        ]
    }), 200
