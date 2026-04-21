from flask import Blueprint, jsonify, request
from database import get_cases_for_user, add_user_to_case

bp_cases = Blueprint("bp_cases", __name__)

@bp_cases.route("/api/cases", methods=["GET"])
def api_get_cases():
    user_id = request.args.get("user_id")
    role = request.args.get("role", "user")

    cases = get_cases_for_user(user_id, role)
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


@bp_cases.route("/api/case/add-user", methods=["POST"])
def api_add_user_to_case():
    body = request.get_json(silent=True) or {}

    case_id = (body.get("case_id") or "").strip()
    user_id = body.get("user_id")

    if not case_id or not user_id:
        return jsonify({
            "ok": False,
            "error": "case_id and user_id required"
        }), 400

    ok = add_user_to_case(case_id, user_id)

    if not ok:
        return jsonify({
            "ok": False,
            "error": "failed to add user"
        }), 400

    return jsonify({
        "ok": True,
        "message": "User added to case"
    }), 200
