import os
import subprocess
import hashlib

def _adb():
    local_adb = os.path.join(os.path.dirname(__file__), "adb.exe")
    if os.path.exists(local_adb):
        return local_adb
    return "adb"

def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def _run(cmd):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

def pull_whatsapp_evidence(case_id="Case_001"):
    save_path = os.path.join("Cases", case_id, "Evidence")
    os.makedirs(save_path, exist_ok=True)

    adb = _adb()
    serial = os.environ.get("ANDROID_SERIAL", "").strip()

    base_cmd = [adb]
    if serial:
        base_cmd += ["-s", serial]

    # =========================
    # dynamic DB path
    # =========================
    possible_paths = [
        "/sdcard/WhatsApp/Databases/",
        "/sdcard/Android/media/com.whatsapp/WhatsApp/Databases/",
        "/storage/emulated/0/WhatsApp/Databases/"
    ]

    android_db = None

    for path in possible_paths:
        res = _run(base_cmd + ["shell", "ls", "-t", path])
        if res.returncode == 0 and res.stdout:
            files = [f.strip() for f in res.stdout.splitlines() if f.strip()]

            preferred = next(
                (f for f in files if f == "msgstore.db.crypt14"),
                None
            )

            if preferred:
                android_db = path + preferred
                print(f"[INFO] Using main DB path: {android_db}")
                break

            fallback = next(
                (f for f in files if "msgstore" in f and "crypt" in f),
                None
            )

            if fallback:
                android_db = path + fallback
                print(f"[INFO] Using fallback DB path: {android_db}")
                break

    android_key = "/data/data/com.whatsapp/files/key"

    local_db_path = os.path.join(save_path, "msgstore.db.crypt14")
    local_key_path = os.path.join(save_path, "key")

    results = []
    success_count = 0

    # =========================
    # 1) Pull database
    # =========================
    try:
        if not android_db:
            raise Exception("WhatsApp database not found")

        res = _run(base_cmd + ["pull", android_db, local_db_path])

        if res.returncode != 0:
            raise Exception(res.stderr or res.stdout)

        db_hash = calculate_sha256(local_db_path)
        db_size = os.path.getsize(local_db_path)

        results.append({
            "file": "msgstore.db.crypt14",
            "status": "Success",
            "hash": db_hash,
            "size": f"{db_size / 1024:.2f} KB",
            "path": local_db_path
        })
        success_count += 1

    except Exception as e:
        results.append({
            "file": "msgstore.db.crypt14",
            "status": "Failed",
            "error": str(e)
        })

    # =========================
    # 2) Pull key
    # =========================
    try:
        temp_key_on_sdcard = "/sdcard/key"

        res_cp = _run(base_cmd + ["shell", "su", "-c", f"cp {android_key} {temp_key_on_sdcard}"])
        if res_cp.returncode != 0:
            raise Exception(res_cp.stderr or res_cp.stdout)

        res_pull = _run(base_cmd + ["pull", temp_key_on_sdcard, local_key_path])
        if res_pull.returncode != 0:
            raise Exception(res_pull.stderr or res_pull.stdout)

        try:
            _run(base_cmd + ["shell", "rm", temp_key_on_sdcard])
        except Exception:
            pass

        key_hash = calculate_sha256(local_key_path)
        key_size = os.path.getsize(local_key_path)

        results.append({
            "file": "key",
            "status": "Success",
            "hash": key_hash,
            "size": f"{key_size / 1024:.2f} KB",
            "path": local_key_path
        })
        success_count += 1

    except Exception as e:
        results.append({
            "file": "key",
            "status": "Failed",
            "error": str(e)
        })

    return {
        "ok": success_count == 2,
        "case_id": case_id,
        "save_path": save_path,
        "total_files": 2,
        "success_count": success_count,
        "failed_count": 2 - success_count,
        "results": results
    }