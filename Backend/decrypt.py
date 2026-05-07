import os
import subprocess
from datetime import datetime


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _resolve_wadecrypt_path(wadecrypt_path: str = "wadecrypt") -> str:
    """
    Finds wadecrypt automatically.

    Priority:
    1. Path passed manually
    2. wadecrypt.exe in same Backend folder
    3. wadecrypt in same Backend folder
    4. fallback to PATH
    """

    # If user passed full path and it exists
    if wadecrypt_path and os.path.exists(wadecrypt_path):
        return wadecrypt_path

    backend_dir = os.path.dirname(os.path.abspath(__file__))

    possible_paths = [
        os.path.join(backend_dir, "wadecrypt.exe"),
        os.path.join(backend_dir, "wadecrypt"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    # fallback: let system search PATH
    return wadecrypt_path


def decrypt_whatsapp_db(
    case_id: str,
    base_cases_dir: str = "Cases",
    wadecrypt_path: str = "wadecrypt",
    crypt_filename: str = "msgstore.db.crypt14",
    key_filename: str = "key",
    out_filename: str = "msgstore_decrypted.db",
    timeout_sec: int = 180
) -> dict:
    """
    Step 3: Decryption (Backend)

    Inputs expected:
      Cases/<case_id>/Evidence/key
      Cases/<case_id>/Evidence/msgstore.db.crypt14

    Output:
      Cases/<case_id>/Decrypted/msgstore_decrypted.db
    """

    case_dir = os.path.join(base_cases_dir, case_id)
    evidence_dir = os.path.join(case_dir, "Evidence")
    decrypted_dir = os.path.join(case_dir, "Decrypted")

    key_path = os.path.join(evidence_dir, key_filename)
    crypt_path = os.path.join(evidence_dir, crypt_filename)
    out_db_path = os.path.join(decrypted_dir, out_filename)

    if not os.path.exists(key_path):
        return {
            "ok": False,
            "step": "decrypt",
            "error": f"Missing key file: {key_path}"
        }

    if not os.path.exists(crypt_path):
        return {
            "ok": False,
            "step": "decrypt",
            "error": f"Missing crypt DB: {crypt_path}"
        }

    _ensure_dir(decrypted_dir)

    resolved_wadecrypt = _resolve_wadecrypt_path(wadecrypt_path)

    cmd = [
        resolved_wadecrypt,
        key_path,
        crypt_path,
        out_db_path
    ]

    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False
        )

        if p.returncode != 0:
            return {
                "ok": False,
                "step": "decrypt",
                "error": "wadecrypt failed",
                "wadecrypt_path": resolved_wadecrypt,
                "returncode": p.returncode,
                "stdout": (p.stdout or "").strip(),
                "stderr": (p.stderr or "").strip(),
            }

        if (not os.path.exists(out_db_path)) or os.path.getsize(out_db_path) == 0:
            return {
                "ok": False,
                "step": "decrypt",
                "error": "Decrypted DB not created or empty",
                "wadecrypt_path": resolved_wadecrypt,
                "stdout": (p.stdout or "").strip(),
                "stderr": (p.stderr or "").strip(),
            }

        return {
            "ok": True,
            "step": "decrypt",
            "case_id": case_id,
            "decrypted_db": out_db_path,
            "wadecrypt_path": resolved_wadecrypt,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "stdout": (p.stdout or "").strip(),
            "stderr": (p.stderr or "").strip(),
        }

    except FileNotFoundError:
        return {
            "ok": False,
            "step": "decrypt",
            "error": (
                "wadecrypt not found. Put wadecrypt.exe or wadecrypt "
                "inside the Backend folder, or pass wadecrypt_path manually."
            ),
            "wadecrypt_path": resolved_wadecrypt,
        }

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "step": "decrypt",
            "error": f"Timeout after {timeout_sec}s",
            "wadecrypt_path": resolved_wadecrypt,
        }