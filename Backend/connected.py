import os
import subprocess
from datetime import datetime
from flask import Blueprint, request, jsonify, redirect
from urllib.parse import quote

from acquisition import pull_whatsapp_evidence
from database import create_next_case, create_case_record

try:
    from decrypt import decrypt_whatsapp_db
except Exception:
    decrypt_whatsapp_db = None

bp_connected = Blueprint("bp_connected", __name__)


def now_ts():
    return datetime.now().isoformat(timespec="seconds")


def safe_str(value):
    try:
        if isinstance(value, str):
            return value
        return str(value)
    except Exception:
        return "<unprintable>"


def add_log(logs, level, msg, step=None, detail=None):
    item = {
        "ts": now_ts(),
        "level": level,
        "msg": msg
    }
    if step:
        item["step"] = step
    if detail is not None:
        item["detail"] = detail
    logs.append(item)

    print(f"[{item['ts']}] [{level}] [{step or '-'}] {msg}")
    if detail is not None:
        print(f"DETAIL: {safe_str(detail)}")


def _run(cmd, timeout=30):
    print(f"[RUN] {' '.join(cmd)}")
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False
    )

    print(f"[RUN RETURN CODE] {p.returncode}")
    if p.stdout:
        print(f"[RUN STDOUT]\n{p.stdout.strip()}")
    if p.stderr:
        print(f"[RUN STDERR]\n{p.stderr.strip()}")

    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def _adb(adb_path=None):
    if adb_path:
        return adb_path

    local_adb = os.path.join(os.path.dirname(__file__), "adb.exe")
    if os.path.exists(local_adb):
        return local_adb

    return "adb"


def adb_version(adb_path=None):
    adb = _adb(adb_path)
    try:
        code, out, err = _run([adb, "version"], timeout=15)
        return {
            "ok": code == 0,
            "returncode": code,
            "stdout": out,
            "stderr": err
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "adb executable not found"
        }
    except Exception as e:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e)
        }


def adb_devices(adb_path=None):
    adb = _adb(adb_path)

    try:
        code, out, err = _run([adb, "devices"], timeout=20)
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "adb_not_found",
            "stdout": "",
            "stderr": "adb executable not found",
            "devices": [],
            "unauthorized": [],
            "offline": []
        }
    except Exception as e:
        return {
            "ok": False,
            "error": "adb_devices_exception",
            "stdout": "",
            "stderr": str(e),
            "devices": [],
            "unauthorized": [],
            "offline": []
        }

    if code != 0:
        return {
            "ok": False,
            "error": "adb_devices_failed",
            "stdout": out,
            "stderr": err,
            "devices": [],
            "unauthorized": [],
            "offline": []
        }

    devices = []
    unauthorized = []
    offline = []

    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        serial = parts[0]
        status = parts[1]

        if status == "device":
            devices.append(serial)
        elif status == "unauthorized":
            unauthorized.append(serial)
        elif status == "offline":
            offline.append(serial)

    return {
        "ok": True,
        "devices": devices,
        "unauthorized": unauthorized,
        "offline": offline,
        "stdout": out,
        "stderr": err
    }


def adb_connect_wifi(ip_port, adb_path=None):
    adb = _adb(adb_path)

    try:
        code, out, err = _run([adb, "connect", ip_port], timeout=25)
    except FileNotFoundError:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "adb executable not found"
        }
    except Exception as e:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e)
        }

    text = (out + " " + err).lower()
    ok = (code == 0) and ("connected" in text or "already connected" in text)

    return {
        "ok": ok,
        "returncode": code,
        "stdout": out,
        "stderr": err
    }


def adb_root_check(serial=None, adb_path=None):
    adb = _adb(adb_path)
    base = [adb]

    if serial:
        base += ["-s", serial]

    try:
        code, out, err = _run(base + ["shell", "su", "-c", "id"], timeout=20)
        if code == 0 and "uid=0" in out:
            return {
                "ok": True,
                "rooted": True,
                "method": "su",
                "stdout": out,
                "stderr": err
            }

        code2, out2, err2 = _run(base + ["shell", "id"], timeout=20)
        if code2 == 0 and "uid=0" in out2:
            return {
                "ok": True,
                "rooted": True,
                "method": "id",
                "stdout": out2,
                "stderr": err2
            }

        return {
            "ok": True,
            "rooted": False,
            "method": "su/id",
            "stdout": out or out2,
            "stderr": err or err2
        }

    except Exception as e:
        return {
            "ok": False,
            "rooted": False,
            "method": "exception",
            "stdout": "",
            "stderr": str(e)
        }


def choose_target_serial(method, ip_port, dev_after):
    devices = dev_after.get("devices") or []

    if method == "wifi":
        if ip_port in devices:
            return {
                "ok": True,
                "serial": ip_port,
                "reason": "Matched Wi-Fi target by exact IP:PORT"
            }

        normalized_ip = ip_port.split(":")[0] if ip_port else ""
        for s in devices:
            if s == normalized_ip or s.startswith(normalized_ip + ":"):
                return {
                    "ok": True,
                    "serial": s,
                    "reason": "Matched Wi-Fi target by normalized IP"
                }

        return {
            "ok": False,
            "error": "Connected device not found in adb devices list",
            "detail": {
                "expected": ip_port,
                "devices": devices
            }
        }

    if len(devices) == 1:
        return {
            "ok": True,
            "serial": devices[0],
            "reason": "Single active USB device found"
        }

    if len(devices) > 1:
        return {
            "ok": False,
            "error": "Multiple active devices found. USB target is ambiguous.",
            "detail": {
                "devices": devices
            }
        }

    return {
        "ok": False,
        "error": "No active device found",
        "detail": {
            "devices": devices
        }
    }


def perform_connect(method, ip_port="", adb_path=None):
    logs = []

    new_case = create_next_case()
    case_id = new_case.case_name

    add_log(logs, "INFO", "Starting device connection flow...", "start")
    add_log(logs, "INFO", f"New case created: {case_id}", "case_create")
    add_log(logs, "INFO", f"Method = {method}", "input")
    add_log(logs, "INFO", f"IP:PORT = {ip_port or '<empty>'}", "input")

    if method not in ("wifi", "usb"):
        add_log(logs, "ERROR", "Invalid connection method.", "validate")
        return {
            "ok": False,
            "step": "validate",
            "error": "method must be wifi or usb",
            "logs": logs
        }, 400

    if method == "wifi" and not ip_port:
        add_log(logs, "ERROR", "WiFi requires ip_port.", "validate")
        return {
            "ok": False,
            "step": "validate",
            "error": "ip_port is required for wifi",
            "logs": logs
        }, 400

    add_log(logs, "INFO", "Checking ADB availability...", "adb_check")
    adb_ver = adb_version(adb_path=adb_path)
    if not adb_ver.get("ok"):
        add_log(logs, "ERROR", "ADB is not available.", "adb_check", adb_ver)
        return {
            "ok": False,
            "step": "adb_check",
            "error": "ADB not found or not working",
            "detail": adb_ver,
            "logs": logs
        }, 400

    add_log(logs, "SUCCESS", "ADB is available.", "adb_check")

    add_log(logs, "INFO", "Checking connected devices before connect...", "devices_before")
    dev_before = adb_devices(adb_path=adb_path)

    if not dev_before.get("ok"):
        add_log(logs, "ERROR", "Failed to list ADB devices.", "devices_before", dev_before)
        return {
            "ok": False,
            "step": "devices_before",
            "error": "Failed to list ADB devices",
            "detail": dev_before,
            "logs": logs
        }, 400

    add_log(logs, "INFO", f"Devices before connect: {dev_before.get('devices', [])}", "devices_before")

    if method == "wifi":
        add_log(logs, "INFO", f"Trying ADB connect to {ip_port}...", "adb_connect")
        conn = adb_connect_wifi(ip_port, adb_path=adb_path)

        if not conn.get("ok"):
            add_log(logs, "ERROR", "ADB connect failed.", "adb_connect", conn)
            return {
                "ok": False,
                "step": "adb_connect",
                "error": "ADB connect failed",
                "detail": conn,
                "logs": logs
            }, 400

        add_log(logs, "SUCCESS", "ADB connect succeeded.", "adb_connect")

    add_log(logs, "INFO", "Refreshing devices after connect...", "devices_after")
    dev_after = adb_devices(adb_path=adb_path)

    if not dev_after.get("ok"):
        add_log(logs, "ERROR", "Failed to refresh devices.", "devices_after", dev_after)
        return {
            "ok": False,
            "step": "devices_after",
            "error": "Failed to refresh devices",
            "detail": dev_after,
            "logs": logs
        }, 400

    add_log(logs, "INFO", f"Devices after connect: {dev_after.get('devices', [])}", "devices_after")

    if not dev_after.get("devices"):
        add_log(logs, "ERROR", "No active device found.", "devices_after", dev_after)
        return {
            "ok": False,
            "step": "devices_after",
            "error": "No active device found",
            "detail": dev_after,
            "logs": logs
        }, 400

    chosen = choose_target_serial(method, ip_port, dev_after)
    if not chosen.get("ok"):
        add_log(logs, "ERROR", chosen.get("error", "Could not determine target serial"), "serial_select", chosen.get("detail"))
        return {
            "ok": False,
            "step": "serial_select",
            "error": chosen.get("error", "Could not determine target serial"),
            "detail": chosen.get("detail"),
            "logs": logs
        }, 400

    serial = chosen["serial"]
    add_log(logs, "SUCCESS", f"Selected device serial: {serial}", "serial_select", {"reason": chosen.get("reason")})

    add_log(logs, "INFO", "Checking root access...", "root_check")
    root = adb_root_check(serial=serial, adb_path=adb_path)

    if not root.get("ok"):
        add_log(logs, "ERROR", "Root check execution failed.", "root_check", root)
        return {
            "ok": False,
            "step": "root_check",
            "error": "Root check failed to execute",
            "detail": root,
            "logs": logs
        }, 400

    if not root.get("rooted"):
        add_log(logs, "ERROR", "Device is not rooted.", "root_check", root)
        return {
            "ok": False,
            "step": "root_check",
            "error": "Device is NOT rooted",
            "detail": root,
            "logs": logs
        }, 403

    add_log(logs, "SUCCESS", "Root access confirmed.", "root_check")

    return {
        "ok": True,
        "step": "connected",
        "case_id": case_id,
        "serial": serial,
        "rooted": True,
        "logs": logs
    }, 200


def perform_workflow(case_id, serial="", wadecrypt_path="wadecrypt", timeout_sec=180):
    logs = []

    if not case_id:
        new_case = create_next_case()
        case_id = new_case.case_name
    else:
        create_case_record(case_id)

    add_log(logs, "INFO", f"Starting workflow for case: {case_id}", "workflow_start")

    old_android_serial = os.environ.get("ANDROID_SERIAL")
    if serial:
        os.environ["ANDROID_SERIAL"] = serial
        add_log(logs, "INFO", f"Using device serial: {serial}", "serial_bind")

    try:
        add_log(logs, "INFO", "Running acquisition...", "acquisition")
        acq = pull_whatsapp_evidence(case_id)

        if not isinstance(acq, dict):
            add_log(logs, "ERROR", "Acquisition returned invalid format.", "acquisition", acq)
            return {
                "ok": False,
                "step": "acquisition",
                "error": "Acquisition returned invalid data",
                "detail": acq,
                "logs": logs
            }, 400

        if not acq.get("ok"):
            add_log(logs, "ERROR", "Acquisition failed.", "acquisition", acq)
            return {
                "ok": False,
                "step": "acquisition",
                "error": "Acquisition failed",
                "detail": acq,
                "logs": logs
            }, 400

        add_log(logs, "SUCCESS", "Acquisition completed successfully.", "acquisition")

        if decrypt_whatsapp_db is None:
            add_log(logs, "ERROR", "decrypt.py is missing or failed to import.", "decrypt")
            return {
                "ok": False,
                "step": "decrypt",
                "error": "decrypt.py not available",
                "logs": logs
            }, 500

        add_log(logs, "INFO", "Running decryption...", "decrypt")
        dec = decrypt_whatsapp_db(
            case_id=case_id,
            wadecrypt_path=wadecrypt_path,
            timeout_sec=timeout_sec
        )

        if not isinstance(dec, dict):
            add_log(logs, "ERROR", "Decryption returned invalid format.", "decrypt", dec)
            return {
                "ok": False,
                "step": "decrypt",
                "error": "Decryption returned invalid data",
                "detail": dec,
                "logs": logs
            }, 400

        if not dec.get("ok"):
            add_log(logs, "ERROR", "Decryption failed.", "decrypt", dec)
            return {
                "ok": False,
                "step": "decrypt",
                "error": "Decryption failed",
                "detail": dec,
                "logs": logs
            }, 400

        add_log(logs, "SUCCESS", "Decryption completed successfully.", "decrypt")

        return {
            "ok": True,
            "case_id": case_id,
            "serial": serial,
            "acquisition": acq,
            "decrypt": dec,
            "logs": logs
        }, 200

    except Exception as e:
        add_log(logs, "ERROR", "Workflow crashed with exception.", "workflow_exception", str(e))
        return {
            "ok": False,
            "step": "workflow_exception",
            "error": "Workflow exception",
            "detail": str(e),
            "logs": logs
        }, 500

    finally:
        if old_android_serial is None:
            os.environ.pop("ANDROID_SERIAL", None)
        else:
            os.environ["ANDROID_SERIAL"] = old_android_serial


@bp_connected.route("/api/device/connect", methods=["POST"])
def api_device_connect():
    body = request.get_json(silent=True) or {}

    print("\n" + "=" * 80)
    print("[API] /api/device/connect called")
    print(f"[BODY] {body}")
    print("=" * 80)

    method = (body.get("method") or "").strip().lower()
    ip_port = (body.get("ip_port") or "").strip()
    adb_path = body.get("adb_path") or None

    result, status = perform_connect(method=method, ip_port=ip_port, adb_path=adb_path)
    return jsonify(result), status


@bp_connected.route("/api/workflow/run", methods=["POST"])
def api_workflow_run():
    body = request.get_json(silent=True) or {}

    print("\n" + "=" * 80)
    print("[API] /api/workflow/run called")
    print(f"[BODY] {body}")
    print("=" * 80)

    case_id = (body.get("case_id") or "").strip()
    serial = (body.get("serial") or "").strip()
    wadecrypt_path = body.get("wadecrypt_path") or "wadecrypt"
    timeout_sec = int(body.get("timeout_sec") or 180)

    result, status = perform_workflow(
        case_id=case_id,
        serial=serial,
        wadecrypt_path=wadecrypt_path,
        timeout_sec=timeout_sec
    )
    return jsonify(result), status


@bp_connected.route("/api/device/connect-and-run", methods=["POST"])
def api_device_connect_and_run():
    body = request.get_json(silent=True) or {}

    print("\n" + "=" * 80)
    print("[API] /api/device/connect-and-run called")
    print(f"[BODY] {body}")
    print("=" * 80)

    method = (body.get("method") or "").strip().lower()
    ip_port = (body.get("ip_port") or "").strip()
    adb_path = body.get("adb_path") or None
    wadecrypt_path = body.get("wadecrypt_path") or "wadecrypt"
    timeout_sec = int(body.get("timeout_sec") or 180)

    conn_result, conn_status = perform_connect(method=method, ip_port=ip_port, adb_path=adb_path)
    if conn_status != 200:
        return jsonify(conn_result), conn_status

    case_id = conn_result.get("case_id", "")
    serial = conn_result.get("serial", "")

    wf_result, wf_status = perform_workflow(
        case_id=case_id,
        serial=serial,
        wadecrypt_path=wadecrypt_path,
        timeout_sec=timeout_sec
    )

    merged_logs = (conn_result.get("logs") or []) + (wf_result.get("logs") or [])

    if wf_status != 200:
        wf_result["case_id"] = case_id
        wf_result["serial"] = serial
        wf_result["logs"] = merged_logs
        return jsonify(wf_result), wf_status

    return jsonify({
        "ok": True,
        "step": "done",
        "case_id": case_id,
        "serial": serial,
        "rooted": True,
        "acquisition": wf_result.get("acquisition"),
        "decrypt": wf_result.get("decrypt"),
        "logs": merged_logs
    }), 200


@bp_connected.route("/api/device/connect-and-open", methods=["GET"])
def api_device_connect_and_open():
    print("\n" + "=" * 80)
    print("[API] /api/device/connect-and-open called")
    print(f"[ARGS] {dict(request.args)}")
    print("=" * 80)

    method = (request.args.get("method") or "").strip().lower()
    ip_port = (request.args.get("ip_port") or "").strip()
    adb_path = request.args.get("adb_path") or None
    wadecrypt_path = request.args.get("wadecrypt_path") or "wadecrypt"
    timeout_sec = int(request.args.get("timeout_sec") or 180)
    frontend_base = (request.args.get("frontend_base") or "").strip()

    if not frontend_base:
        return jsonify({
            "ok": False,
            "error": "frontend_base is required"
        }), 400

    conn_result, conn_status = perform_connect(
        method=method,
        ip_port=ip_port,
        adb_path=adb_path
    )

    if conn_status != 200:
        return jsonify(conn_result), conn_status

    case_id = conn_result.get("case_id", "")
    serial = conn_result.get("serial", "")

    wf_result, wf_status = perform_workflow(
        case_id=case_id,
        serial=serial,
        wadecrypt_path=wadecrypt_path,
        timeout_sec=timeout_sec
    )

    if wf_status != 200:
        merged_logs = (conn_result.get("logs") or []) + (wf_result.get("logs") or [])
        wf_result["case_id"] = case_id
        wf_result["serial"] = serial
        wf_result["logs"] = merged_logs
        return jsonify(wf_result), wf_status

    target = f"{frontend_base.rstrip('/')}/chat.html?case_id={quote(case_id)}"
    print(f"[REDIRECT] {target}")
    return redirect(target, code=302)