from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    job_title = db.Column(db.String(150), nullable=True)
    department = db.Column(db.String(150), nullable=True)

    role = db.Column(db.String(20), default="user")   # admin / user
    is_active = db.Column(db.Boolean, default=True)

    approved_at = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "job_title": self.job_title,
            "department": self.department,
            "role": self.role,
            "is_active": self.is_active,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }


class AccountRequest(db.Model):
    __tablename__ = "account_requests"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    job_title = db.Column(db.String(150), nullable=True)
    department = db.Column(db.String(150), nullable=True)
    reason = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), default="pending")  # pending / approved / rejected

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "job_title": self.job_title,
            "department": self.department,
            "reason": self.reason,
            "status": self.status,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by
        }


class Case(db.Model):
    __tablename__ = "cases"

    id = db.Column(db.Integer, primary_key=True)
    case_name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CaseInvestigator(db.Model):
    __tablename__ = "case_investigators"

    id = db.Column(db.Integer, primary_key=True)
    case_name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    added_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

class EvidenceHash(db.Model):
    __tablename__ = "evidence_hashes"

    id = db.Column(db.Integer, primary_key=True)

    case_name = db.Column(db.String(150), nullable=False)
    file_name = db.Column(db.String(150), nullable=False)

    sha256_hash = db.Column(db.String(64), nullable=False)
    file_size = db.Column(db.String(50), nullable=True)
    file_path = db.Column(db.String(300), nullable=True)
    device_sha256_hash = db.Column(db.String(64), nullable=True)
    local_sha256_hash = db.Column(db.String(64), nullable=True)
    integrity_status = db.Column(db.String(30), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)