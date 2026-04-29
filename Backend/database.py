"""
Database Helper Functions for Whisper-WA
"""

import os
from models import db, User, AccountRequest, Case, CaseInvestigator, EvidenceHash
from datetime import datetime


def init_database(app):
    """
    Initialize database and create all tables
    """
    with app.app_context():
        db.create_all()
        print("✓ Database tables created successfully")

        create_default_admin()
        print("✓ Default admin user initialized")

        synced = sync_cases_from_folders()
        print(f"✓ Synced {synced} existing case(s) from folders")


def create_default_admin():
    """
    Create default admin user
    Email: admin@whisper-wa.local
    Password: admin123
    """
    admin_email = "admin@whisper-wa.local"

    existing_admin = User.query.filter_by(email=admin_email).first()

    if not existing_admin:
        admin = User(
            name="System Administrator",
            email=admin_email,
            job_title="System Admin",
            department="IT Security",
            role="admin",
            is_active=True,
            approved_at=datetime.utcnow()
        )
        admin.set_password("admin123")

        db.session.add(admin)
        db.session.commit()
        print(f"✓ Default admin created: {admin_email}")
    else:
        print(f"✓ Admin already exists: {admin_email}")


def get_pending_requests_count():
    return AccountRequest.query.filter_by(status='pending').count()


def get_active_users_count():
    return User.query.filter_by(is_active=True).count()


def get_user_by_email(email):
    return User.query.filter_by(email=email).first()


def get_user_by_id(user_id):
    return User.query.get(user_id)


def get_request_by_id(request_id):
    return AccountRequest.query.get(request_id)


def create_user_from_request(request_obj, approved_by_id):
    """
    Create user from approved request
    Uses the SAME password submitted in the request
    """
    existing_user = User.query.filter_by(email=request_obj.email).first()
    if existing_user:
        return None

    user = User(
        name=request_obj.name,
        email=request_obj.email,
        job_title=request_obj.job_title,
        department=request_obj.department,
        role='user',
        is_active=True,
        approved_at=datetime.utcnow()
    )

    user.password_hash = request_obj.password_hash

    request_obj.status = 'approved'
    request_obj.reviewed_at = datetime.utcnow()
    request_obj.reviewed_by = approved_by_id

    db.session.add(user)
    db.session.commit()

    return user


def get_all_requests(status=None):
    if status:
        return AccountRequest.query.filter_by(status=status).order_by(
            AccountRequest.submitted_at.desc()
        ).all()
    else:
        return AccountRequest.query.order_by(
            AccountRequest.submitted_at.desc()
        ).all()


def get_all_active_users():
    return User.query.filter_by(is_active=True).order_by(
        User.approved_at.desc()
    ).all()


def deactivate_user(user_id):
    user = User.query.get(user_id)

    if not user:
        return False

    if user.role == 'admin':
        return False

    user.is_active = False
    db.session.commit()

    return True


def get_admin_stats():
    return {
        'pending_requests': AccountRequest.query.filter_by(status='pending').count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'rejected_requests': AccountRequest.query.filter_by(status='rejected').count(),
        'total_requests': AccountRequest.query.count(),
        'total_cases': Case.query.count()
    }


def search_users(query):
    search_pattern = f"%{query}%"
    return User.query.filter(
        (User.name.like(search_pattern)) | (User.email.like(search_pattern))
    ).all()


def reject_request(request_id, reviewed_by_id):
    request_obj = AccountRequest.query.get(request_id)

    if not request_obj:
        return False

    request_obj.status = 'rejected'
    request_obj.reviewed_at = datetime.utcnow()
    request_obj.reviewed_by = reviewed_by_id

    db.session.commit()

    return True


def cleanup_old_requests(days=30):
    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    old_requests = AccountRequest.query.filter(
        AccountRequest.status.in_(['rejected', 'approved']),
        AccountRequest.reviewed_at < cutoff_date
    ).all()

    count = len(old_requests)

    for request_obj in old_requests:
        db.session.delete(request_obj)

    db.session.commit()

    return count


def _extract_case_number(case_name):
    try:
        if not case_name:
            return None
        if not case_name.startswith("Case_"):
            return None
        return int(case_name.split("_")[1])
    except Exception:
        return None


def get_case_by_name(case_name):
    return Case.query.filter_by(case_name=case_name).first()


def get_all_cases():
    return Case.query.order_by(Case.created_at.desc()).all()


def get_case_names():
    cases = get_all_cases()
    return [c.case_name for c in cases]


def create_case_record(case_name):
    existing = get_case_by_name(case_name)
    if existing:
        return existing

    new_case = Case(case_name=case_name)
    db.session.add(new_case)
    db.session.commit()
    return new_case


def sync_cases_from_folders(base_cases_dir="Cases"):
    """
    Add old existing case folders into DB if they are not already stored.
    Example: Cases/Case_001 -> cases table
    """
    if not os.path.exists(base_cases_dir):
        return 0

    added_count = 0

    for name in os.listdir(base_cases_dir):
        full_path = os.path.join(base_cases_dir, name)

        if not os.path.isdir(full_path):
            continue

        if not name.startswith("Case_"):
            continue

        existing = get_case_by_name(name)
        if existing:
            continue

        db.session.add(Case(case_name=name))
        added_count += 1

    if added_count > 0:
        db.session.commit()

    return added_count


def generate_next_case_id(base_cases_dir="Cases"):
    """
    Generate next case id by checking BOTH:
    1) cases table in database
    2) Cases folders on disk
    """
    max_num = 0

    
    db_cases = Case.query.all()
    for c in db_cases:
        n = _extract_case_number(c.case_name)
        if n is not None and n > max_num:
            max_num = n

    if os.path.exists(base_cases_dir):
        for name in os.listdir(base_cases_dir):
            full_path = os.path.join(base_cases_dir, name)
            if os.path.isdir(full_path):
                n = _extract_case_number(name)
                if n is not None and n > max_num:
                    max_num = n

    next_num = max_num + 1
    return f"Case_{next_num:03d}"


def create_next_case(base_cases_dir="Cases"):
    """
    Create a brand-new case every time.
    """
    case_name = generate_next_case_id(base_cases_dir=base_cases_dir)
    return create_case_record(case_name)


def assign_case_owner(case_name, user_id):
    if not user_id:
        return

    existing = CaseInvestigator.query.filter_by(
        case_name=case_name,
        user_id=user_id
    ).first()

    if not existing:
        db.session.add(CaseInvestigator(
            case_name=case_name,
            user_id=user_id,
            
        ))
        db.session.commit()


def add_investigator_to_case(case_name, user_id):
    existing = CaseInvestigator.query.filter_by(
        case_name=case_name,
        user_id=user_id
    ).first()

    if not existing:
        db.session.add(CaseInvestigator(
            case_name=case_name,
            user_id=user_id,
            
        ))
        db.session.commit()


def get_cases_for_user(user_id, role):
    if role == "admin":
        return get_all_cases()

    if not user_id:
        return []

    links = CaseInvestigator.query.filter_by(user_id=user_id).all()
    case_names = [l.case_name for l in links]

    if not case_names:
        return []

    return Case.query.filter(
        Case.case_name.in_(case_names)
    ).order_by(Case.created_at.desc()).all()


def get_case_investigators(case_name):
    return CaseInvestigator.query.filter_by(case_name=case_name).all()

def add_user_to_case(case_name, user_id):
    if not case_name or not user_id:
        return False

    existing = CaseInvestigator.query.filter_by(
        case_name=case_name,
        user_id=user_id
    ).first()

    if existing:
        return True

    db.session.add(CaseInvestigator(
        case_name=case_name,
        user_id=user_id,
        
    ))
    db.session.commit()
    return True

def get_investigators_details(case_name):
    """
    جلب تفاصيل المحققين (الاسم، الآي دي) المرتبطين بقضية معينة
    """
    links = CaseInvestigator.query.filter_by(case_name=case_name).all()
    users_info = []
    
    for link in links:
        user = get_user_by_id(link.user_id) 
        if user:
            users_info.append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                
            })
    return users_info

def remove_user_from_case(case_name, user_id):
    """
    حذف ارتباط محقق بقضية (لا يمكن حذف المالك الأساسي)
    """
    if not case_name or not user_id:
        return False

    link = CaseInvestigator.query.filter_by(
        case_name=case_name,
        user_id=user_id
    ).first()

    if not link:
        return False



    db.session.delete(link)
    db.session.commit()
    return True
def save_evidence_hash(case_name, file_name, file_hash, file_size, file_path,
                       device_hash=None, local_hash=None, integrity_status=None):

    record = EvidenceHash(
        case_name=case_name,
        file_name=file_name,
        sha256_hash=file_hash,
        device_sha256_hash=device_hash,
        local_sha256_hash=local_hash,
        integrity_status=integrity_status,
        file_size=file_size,
        file_path=file_path
    )

    db.session.add(record)
    db.session.commit()
