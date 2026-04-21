from flask import Blueprint, request, jsonify
from datetime import datetime

from models import db, User, AccountRequest
from auth import generate_token, authenticate_user, admin_required, login_required
from database import (
    create_user_from_request,
    get_all_requests,
    get_all_active_users,
    reject_request,
    deactivate_user,
    get_admin_stats,
    search_users
)

bp_auth = Blueprint("bp_auth", __name__)


@bp_auth.route("/api/auth/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}

    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    if not email or not password:
        return jsonify({
            "success": False,
            "message": "Email and password are required"
        }), 400

    success, user, message = authenticate_user(email, password)

    if not success:
        return jsonify({
            "success": False,
            "message": message
        }), 401

    token = generate_token(user)

    return jsonify({
        "success": True,
        "message": message,
        "token": token,
        "user": user.to_dict()
    }), 200


@bp_auth.route("/api/auth/me", methods=["GET"])
@login_required
def me(current_user):
    return jsonify({
        "success": True,
        "user": current_user.to_dict()
    }), 200


@bp_auth.route("/api/auth/register-request", methods=["POST"])
def register_request():
    body = request.get_json(silent=True) or {}

    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    job_title = (body.get("job_title") or "").strip()
    department = (body.get("department") or "").strip()
    reason = (body.get("reason") or "").strip()

    if not name or not email or not password:
        return jsonify({
            "success": False,
            "message": "Name, email, password are required"
        }), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({
            "success": False,
            "message": "An account with this email already exists"
        }), 409

    existing_request = AccountRequest.query.filter_by(email=email, status="pending").first()
    if existing_request:
        return jsonify({
            "success": False,
            "message": "A pending request already exists for this email"
        }), 409

    new_request = AccountRequest(
        name=name,
        email=email,
        job_title=job_title,
        department=department or "Not specified",
        reason=reason,
        status="pending",
        submitted_at=datetime.utcnow()
    )
    new_request.set_password(password)

    db.session.add(new_request)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Request submitted successfully",
        "request_id": new_request.id
    }), 201


@bp_auth.route("/api/admin/stats", methods=["GET"])
@admin_required
def admin_stats(current_user):
    return jsonify({
        "success": True,
        "stats": get_admin_stats()
    }), 200


@bp_auth.route("/api/admin/requests", methods=["GET"])
@admin_required
def admin_get_requests(current_user):
    status = request.args.get("status")
    requests_list = get_all_requests(status=status)

    return jsonify({
        "success": True,
        "requests": [r.to_dict() for r in requests_list]
    }), 200


@bp_auth.route("/api/admin/requests/<int:request_id>/approve", methods=["POST"])
@admin_required
def admin_approve_request(current_user, request_id):
    request_obj = AccountRequest.query.get(request_id)

    if not request_obj:
        return jsonify({
            "success": False,
            "message": "Request not found"
        }), 404

    if request_obj.status != "pending":
        return jsonify({
            "success": False,
            "message": "Only pending requests can be approved"
        }), 400

    user = create_user_from_request(request_obj, current_user.id)

    if user is None:
        return jsonify({
            "success": False,
            "message": "User already exists"
        }), 409

    return jsonify({
        "success": True,
        "message": "Request approved successfully",
        "user": user.to_dict()
    }), 200


@bp_auth.route("/api/admin/requests/<int:request_id>/reject", methods=["POST"])
@admin_required
def admin_reject_request(current_user, request_id):
    ok = reject_request(request_id, current_user.id)

    if not ok:
        return jsonify({
            "success": False,
            "message": "Request not found"
        }), 404

    return jsonify({
        "success": True,
        "message": "Request rejected successfully"
    }), 200
@bp_auth.route("/api/users/list", methods=["GET"])
def users_list():
    query = (request.args.get("q") or "").strip()

    if query:
        users = search_users(query)
    else:
        users = get_all_active_users()

    return jsonify({
        "success": True,
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role
            }
            for u in users if u.is_active
        ]
    }), 200

@bp_auth.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_get_users(current_user):
    users = get_all_active_users()

    return jsonify({
        "success": True,
        "users": [u.to_dict() for u in users]
    }), 200


@bp_auth.route("/api/admin/users/<int:user_id>/deactivate", methods=["POST"])
@admin_required
def admin_deactivate_user(current_user, user_id):
    ok = deactivate_user(user_id)

    if not ok:
        return jsonify({
            "success": False,
            "message": "User not found or cannot deactivate admin"
        }), 400

    return jsonify({
        "success": True,
        "message": "User deactivated successfully"
    }), 200
