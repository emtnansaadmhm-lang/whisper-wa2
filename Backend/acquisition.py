import os
import subprocess
import hashlib
from database import save_evidence_hash


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


def calculate_device_sha256(base_cmd, android_path):
    commands = [
        ["shell", "sha256sum", android_path],
        ["shell", "su", "-c", f"sha256sum {android_path}"]
    ]

    for cmd in commands:
        res = _run(base_cmd + cmd)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split()[0]

    return None


def pull_whatsapp_evidence(case_id="Case_001"):
    save_path = os.path.join("Cases", case_id, "Evidence")
    os.makedirs(save_path, exist_ok=True)

    adb = _adb()
    serial = os.environ.get("ANDROID_SERIAL", "").strip()

    base_cmd = [adb]
    if serial:
        base_cmd += ["-s", serial]

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

            preferred = next((f for f in files if f == "msgstore.db.crypt14"), None)

            if preferred:
                android_db = path + preferred
                print(f"[INFO] Using main DB path: {android_db}")
                break

            fallback = next((f for f in files if "msgstore" in f and "crypt" in f), None)

            if fallback:
                android_db = path + fallback
                print(f"[INFO] Using fallback DB path: {android_db}")
                break

    local_db_path = os.path.join(save_path, "msgstore.db.crypt14")
    local_key_path = os.path.join(save_path, "key")
    local_media_path = os.path.join(save_path, "Media")

    results = []
    success_count = 0

    # =========================
    # 1) Pull database
    # =========================
    try:
        if not android_db:
            raise Exception("WhatsApp database not found")

        db_device_hash = calculate_device_sha256(base_cmd, android_db)

        res = _run(base_cmd + ["pull", android_db, local_db_path])
        if res.returncode != 0:
            raise Exception(res.stderr or res.stdout)

        db_hash = calculate_sha256(local_db_path)
        db_size = os.path.getsize(local_db_path)

        db_integrity = (
            "Verified"
            if db_device_hash and db_device_hash == db_hash
            else "Not Verified"
        )

        save_evidence_hash(
            case_id,
            "msgstore.db.crypt14",
            db_hash,
            f"{db_size / 1024:.2f} KB",
            local_db_path,
            device_hash=db_device_hash,
            local_hash=db_hash,
            integrity_status=db_integrity
        )

        results.append({
            "file": "msgstore.db.crypt14",
            "status": "Success",
            "hash": db_hash,
            "device_hash": db_device_hash,
            "local_hash": db_hash,
            "integrity": db_integrity,
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
        is_wifi = bool(serial and ":" in serial)

        key_device_hash = None

        if not is_wifi:
            android_key = "/data/data/com.whatsapp/files/key"

            res_cp = _run(base_cmd + ["shell", "su", "-c", f"cp {android_key} {temp_key_on_sdcard}"])
            if res_cp.returncode != 0:
                raise Exception(res_cp.stderr or res_cp.stdout)

            key_device_hash = calculate_device_sha256(base_cmd, temp_key_on_sdcard)

            res_pull = _run(base_cmd + ["pull", temp_key_on_sdcard, local_key_path])
            if res_pull.returncode != 0:
                raise Exception(res_pull.stderr or res_pull.stdout)

            try:
                _run(base_cmd + ["shell", "rm", temp_key_on_sdcard])
            except Exception:
                pass

        else:
            possible_key_paths = [
                "/data/data/com.whatsapp/files/key",
                "/data/user/0/com.whatsapp/files/key"
            ]

            key_pulled = False
            last_error = ""

            for android_key in possible_key_paths:
                print(f"[INFO] Trying key path: {android_key}")

                res_cp = _run(base_cmd + ["shell", f'su -c "cp {android_key} {temp_key_on_sdcard}"'])
                if res_cp.returncode != 0:
                    last_error = res_cp.stderr or res_cp.stdout or f"Failed to copy key from {android_key}"
                    continue

                _run(base_cmd + ["shell", f'su -c "chmod 666 {temp_key_on_sdcard}"'])

                key_device_hash = calculate_device_sha256(base_cmd, temp_key_on_sdcard)

                res_pull = _run(base_cmd + ["pull", temp_key_on_sdcard, local_key_path])
                if res_pull.returncode != 0:
                    last_error = res_pull.stderr or res_pull.stdout or f"Failed to pull key from {android_key}"
                    continue

                key_pulled = True
                print(f"[INFO] Key pulled successfully from: {android_key}")
                break

            try:
                _run(base_cmd + ["shell", f'su -c "rm -f {temp_key_on_sdcard}"'])
            except Exception:
                pass

            if not key_pulled:
                raise Exception(last_error or "Failed to pull WhatsApp key from all known paths")

        key_hash = calculate_sha256(local_key_path)
        key_size = os.path.getsize(local_key_path)

        key_integrity = (
            "Verified"
            if key_device_hash and key_device_hash == key_hash
            else "Not Verified"
        )

        save_evidence_hash(
            case_id,
            "key",
            key_hash,
            f"{key_size / 1024:.2f} KB",
            local_key_path,
            device_hash=key_device_hash,
            local_hash=key_hash,
            integrity_status=key_integrity
        )

        results.append({
            "file": "key",
            "status": "Success",
            "hash": key_hash,
            "device_hash": key_device_hash,
            "local_hash": key_hash,
            "integrity": key_integrity,
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

    # =========================
    # 3) Pull WhatsApp Media
    # =========================
    try:
        possible_media_paths = [
            "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/",
            "/sdcard/WhatsApp/Media/",
            "/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media/",
            "/storage/emulated/0/WhatsApp/Media/"
        ]

        os.makedirs(local_media_path, exist_ok=True)

        media_pulled = False
        last_media_error = ""

        for media_path in possible_media_paths:
            print(f"[INFO] Trying media path: {media_path}")

            check_res = _run(base_cmd + ["shell", "ls", media_path])
            if check_res.returncode != 0:
                last_media_error = check_res.stderr or check_res.stdout
                continue

            pull_res = _run(base_cmd + ["pull", media_path, local_media_path])
            if pull_res.returncode == 0:
                media_pulled = True
                print(f"[INFO] Media pulled successfully from: {media_path}")
                break

            last_media_error = pull_res.stderr or pull_res.stdout

        if not media_pulled:
            raise Exception(last_media_error or "WhatsApp media folder not found")

        results.append({
            "file": "Media",
            "status": "Success",
            "path": local_media_path
        })

    except Exception as e:
        results.append({
            "file": "Media",
            "status": "Failed",
            "error": str(e)
        })

    return {
        "ok": success_count == 2,
        "case_id": case_id,
        "save_path": save_path,
        "total_files": 3,
        "success_count": success_count,
        "failed_count": 3 - success_count,
        "results": results
    }