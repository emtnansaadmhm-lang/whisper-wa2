from flask import Blueprint, jsonify, request
from database import Case, db

bp_cases = Blueprint("bp_cases", __name__)

@bp_cases.route("/api/cases", methods=["GET"])
def api_get_cases():
    try:
       
        cases = Case.query.all()

       
        cases = sorted(cases, key=lambda c: c.id, reverse=True)

        return jsonify({
            "ok": True,
            "cases": [
                {
                    "id": c.id,
                    "case_id": c.case_name
                }
                for c in cases
            ]
        }), 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"ok": False, "error": str(e)}), 500
