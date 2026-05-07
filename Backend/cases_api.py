from datetime import datetime
import shutil
import os


from flask import Blueprint, jsonify, request

from database import (
    get_cases_for_user,
    add_user_to_case,
    get_investigators_details,
    remove_user_from_case
)

from models import EvidenceHash

bp_cases = Blueprint("bp_cases", __name__)


@bp_cases.route("/api/cases", methods=["GET"])
def api_get_cases():
    user_id = request.args.get("user_id")
    role = request.args.get("role", "user")

    cases = get_cases_for_user(user_id, role)
    # ترتيب القضايا حسب التاريخ
    cases.sort(key=lambda x: x['created_at'] or datetime.min, reverse=True)

    return jsonify({
        "ok": True,
        "cases": [
            {
                "id": c['id'],
                "case_id": c['case_name'],
                "is_owner": c['is_owner'],
                "added_by_name": c['added_by_name'],
                "created_at_text": c['created_at'].strftime("%Y-%m-%d %H:%M:%S") if c['created_at'] else "No date"
            }
            for c in cases
        ]
    }), 200


@bp_cases.route("/api/case/add-user", methods=["POST"])
def api_add_user_to_case():
    body = request.get_json(silent=True) or {}
    case_id = (body.get("case_id") or "").strip()
    user_id = body.get("user_id")
    
    adder_id = body.get("added_by") 

    if not case_id or not user_id:
        return jsonify({"ok": False, "error": "case_id and user_id required"}), 400

    
    ok = add_user_to_case(case_id, user_id, current_user_id=adder_id)

    if not ok:
        return jsonify({"ok": False, "error": "failed to add user"}), 400

    return jsonify({"ok": True, "message": "User added to case"}), 200


@bp_cases.route("/api/case/delete", methods=["POST"])
def api_delete_case():
    body = request.get_json(silent=True) or {}
    case_id = body.get("case_id")

    if not case_id:
        return jsonify({
            "ok": False,
            "error": "Case ID is required"
        }), 400

    try:
        case_path = os.path.join("Cases", case_id)

        if os.path.exists(case_path):
            shutil.rmtree(case_path)

        from models import Case
        from database import db

        case_record = Case.query.filter_by(case_name=case_id).first()
        if case_record:
            db.session.delete(case_record)
            db.session.commit()

        return jsonify({
            "ok": True,
            "message": "Case deleted successfully"
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp_cases.route("/api/case/investigators/<case_id>", methods=["GET"])
def api_get_case_investigators(case_id):
    users = get_investigators_details(case_id)

    return jsonify({
        "ok": True,
        "users": users
    }), 200


@bp_cases.route("/api/case/remove-user", methods=["POST"])
def api_remove_user_from_case():
    body = request.get_json(silent=True) or {}
    case_id = body.get("case_id")
    user_id = body.get("user_id")

    if not case_id or not user_id:
        return jsonify({
            "ok": False,
            "error": "case_id and user_id required"
        }), 400

    success = remove_user_from_case(case_id, user_id)

    if success:
        return jsonify({
            "ok": True,
            "message": "User removed from case successfully"
        }), 200

    return jsonify({
        "ok": False,
        "error": "المحقق غير موجود"
    }), 400


@bp_cases.route("/api/case-integrity/<case_id>", methods=["GET"])
def api_get_case_integrity(case_id):
    records = EvidenceHash.query.filter_by(case_name=case_id).all()

    if not records:
        return jsonify({
            "ok": False,
            "case_id": case_id,
            "integrity": "Unknown"
        }), 200

    statuses = [
        record.integrity_status
        for record in records
        if record.integrity_status
    ]

    if statuses and all(status == "Verified" for status in statuses):
        integrity = "Verified"
    elif statuses:
        integrity = "Not Verified"
    else:
        integrity = "Unknown"

    return jsonify({
        "ok": True,
        "case_id": case_id,
        "integrity": integrity
    }), 200