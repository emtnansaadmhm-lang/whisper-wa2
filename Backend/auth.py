"""
Authentication Functions for Whisper-WA
Handles login, JWT tokens, and route protection
"""

from functools import wraps
from flask import request, jsonify
import jwt
from datetime import datetime, timedelta
from models import User, db

SECRET_KEY = "whisper-wa-secret-key-2026-change-in-production"
TOKEN_EXPIRATION_HOURS = 24


def generate_token(user):
    payload = {
        'user_id': user.id,
        'email': user.email,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(hours=TOKEN_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    return token


def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def authenticate_user(email, password):
    user = User.query.filter_by(email=email).first()

    if not user:
        return False, None, "Invalid email or password"

    if not user.is_active:
        return False, None, "Account has been deactivated. Please contact administrator."

    if not user.check_password(password):
        return False, None, "Invalid email or password"

    user.last_login = datetime.utcnow()
    db.session.commit()

    return True, user, "Login successful"


def get_current_user(token):
    payload = verify_token(token)

    if not payload:
        return None

    user_id = payload.get('user_id')
    user = User.query.get(user_id)

    return user


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid token format. Use: Bearer <token>'
                }), 401

        if not token:
            return jsonify({
                'success': False,
                'message': 'Authentication token is missing'
            }), 401

        current_user = get_current_user(token)

        if not current_user:
            return jsonify({
                'success': False,
                'message': 'Invalid or expired token'
            }), 401

        return f(current_user=current_user, *args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid token format'
                }), 401

        if not token:
            return jsonify({
                'success': False,
                'message': 'Authentication required'
            }), 401

        current_user = get_current_user(token)

        if not current_user:
            return jsonify({
                'success': False,
                'message': 'Invalid or expired token'
            }), 401

        if current_user.role != 'admin':
            return jsonify({
                'success': False,
                'message': 'Admin privileges required'
            }), 403

        return f(current_user=current_user, *args, **kwargs)

    return decorated_function


def optional_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        current_user = None

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
                current_user = get_current_user(token)
            except (IndexError, Exception):
                pass

        return f(current_user=current_user, *args, **kwargs)

    return decorated_function


def validate_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    return True, "Password is valid"


def change_password(user, old_password, new_password):
    if not user.check_password(old_password):
        return False, "Current password is incorrect"

    valid, message = validate_password(new_password)
    if not valid:
        return False, message

    user.set_password(new_password)
    db.session.commit()

    return True, "Password changed successfully"


def reset_password(user, new_password):
    valid, message = validate_password(new_password)
    if not valid:
        return False, message

    user.set_password(new_password)
    db.session.commit()

    return True, "Password reset successfully"