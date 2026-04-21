import os
import sqlite3
from flask import Blueprint, jsonify

messages_api = Blueprint("messages_api", __name__)

BASE_DIR = os.path.dirname(__file__)


def get_db_path(case_id: str) -> str:
    return os.path.join(
        BASE_DIR,
        "Cases",
        case_id,
        "Decrypted",
        "msgstore_decrypted.db"
    )


def get_tables(cur):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cur.fetchall()]


def get_columns(cur, table_name: str):
    cur.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]


def pick_first_existing(tables, candidates):
    for c in candidates:
        if c in tables:
            return c
    return None


def clean_number(value):
    if value is None:
        return "Unknown"

    value = str(value).strip()

    if value in ["status@broadcast", "status_me", "status"]:
        return "Status"

    if value == "lid_me":
        return "Me"

    if "@s.whatsapp.net" in value:
        return value.split("@")[0]

    if "@g.us" in value:
        return value.split("@")[0]

    import re
    match = re.search(r"\d{8,15}", value)
    if match:
        return match.group(0)

    return value


@messages_api.route("/api/messages/<case_id>", methods=["GET"])
def get_messages(case_id):
    db_path = get_db_path(case_id)

    if not os.path.exists(db_path):
        return jsonify({
            "ok": False,
            "error": f"Decrypted DB not found for case {case_id}",
            "path": db_path
        }), 404

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        tables = get_tables(cur)

        # أشهر أسماء الجداول باختلاف نسخ واتساب
        message_table = pick_first_existing(tables, [
            "messages",
            "message",
            "chat_messages"
        ])

        if not message_table:
            conn.close()
            return jsonify({
                "ok": False,
                "error": "Could not find a messages table in decrypted DB",
                "tables": tables
            }), 400

        cols = get_columns(cur, message_table)

        # أعمدة شائعة
        id_col = "_id" if "_id" in cols else ("id" if "id" in cols else None)
        key_id_col = "key_id" if "key_id" in cols else None

        chat_col = None
        for c in ["key_remote_jid", "chat_row_id", "jid_row_id", "remote_jid", "jid"]:
            if c in cols:
                chat_col = c
                break

        text_col = None
        for c in ["data", "text_data", "body", "message", "content"]:
            if c in cols:
                text_col = c
                break

        ts_col = None
        for c in ["timestamp", "message_date", "sort_timestamp", "received_timestamp", "sent_timestamp"]:
            if c in cols:
                ts_col = c
                break

        from_me_col = None
        for c in ["key_from_me", "from_me"]:
            if c in cols:
                from_me_col = c
                break

        if not text_col:
            conn.close()
            return jsonify({
                "ok": False,
                "error": f"Could not find text column in table {message_table}",
                "table": message_table,
                "columns": cols
            }), 400

        selected_cols = []
        selected_cols.append(f"{id_col} AS row_id" if id_col else "NULL AS row_id")
        selected_cols.append(f"{key_id_col} AS key_id" if key_id_col else "NULL AS key_id")
        selected_cols.append(f"{chat_col} AS chat_ref" if chat_col else "NULL AS chat_ref")
        selected_cols.append(f"{text_col} AS msg_text")
        selected_cols.append(f"{ts_col} AS msg_ts" if ts_col else "NULL AS msg_ts")
        selected_cols.append(f"{from_me_col} AS from_me" if from_me_col else "0 AS from_me")

        query = f"""
            SELECT {", ".join(selected_cols)}
            FROM {message_table}
            WHERE {text_col} IS NOT NULL AND TRIM({text_col}) != ''
            ORDER BY {ts_col if ts_col else (id_col if id_col else 'rowid')} ASC
            LIMIT 1000
        """

        cur.execute(query)
        rows = cur.fetchall()

        # محاولة ربط أسماء/أرقام المحادثات إذا chat_ref عبارة عن row id
        chat_names_by_id = {}

        if "jid" in tables:
            jid_cols = get_columns(cur, "jid")

            if "_id" in jid_cols and "user" in jid_cols and "server" in jid_cols:
                select_fields = ["_id", "user", "server"]
                if "raw_string" in jid_cols:
                    select_fields.append("raw_string")

                cur.execute(f"SELECT {', '.join(select_fields)} FROM jid")

                for r in cur.fetchall():
                    jid_id = str(r["_id"])
                    user_val = str(r["user"] or "").strip()
                    server_val = str(r["server"] or "").strip().lower()
                    raw_val = str(r["raw_string"] or "").strip() if "raw_string" in r.keys() else ""

                    display_name = raw_val or user_val or jid_id

                    if server_val == "s.whatsapp.net" and user_val:
                        display_name = user_val
                    elif server_val == "broadcast":
                        display_name = "Status"
                    elif user_val == "status_me":
                        display_name = "Status"
                    elif user_val == "lid_me":
                        display_name = "Me"
                    elif user_val:
                        display_name = user_val

                    chat_names_by_id[jid_id] = display_name

        if "chat" in tables:
            chat_cols = get_columns(cur, "chat")
            if "_id" in chat_cols and "subject" in chat_cols:
                cur.execute("SELECT _id, subject FROM chat WHERE subject IS NOT NULL AND TRIM(subject) != ''")
                for r in cur.fetchall():
                    chat_names_by_id[str(r[0])] = r["subject"]

        conn.close()

        chats_map = {}

        for row in rows:
            row = dict(row)

            raw_chat_ref = row.get("chat_ref")
            chat_ref = str(raw_chat_ref) if raw_chat_ref is not None else "unknown_chat"

            chat_name = chat_names_by_id.get(chat_ref, chat_ref)

            msg_id = row.get("key_id") or row.get("row_id") or ""
            text = row.get("msg_text") or ""
            timestamp = row.get("msg_ts")
            from_me = int(row.get("from_me") or 0)

            display_time = ""
            display_datetime = ""

            try:
                if timestamp is not None:
                    ts = int(timestamp)
                    if ts > 10_000_000_000:
                        import datetime as dt
                        dt_obj = dt.datetime.fromtimestamp(ts / 1000)
                    else:
                        import datetime as dt
                        dt_obj = dt.datetime.fromtimestamp(ts)

                    display_time = dt_obj.strftime("%H:%M")
                    display_datetime = dt_obj.strftime("%Y-%m-%d %H:%M")
            except Exception:
                display_time = ""
                display_datetime = str(timestamp or "")

            if chat_ref not in chats_map:
                chats_map[chat_ref] = {
                    "id": chat_ref,
                    "number": clean_number(chat_name),
                    "name": chat_name,
                    "last_message": text,
                    "last_time": display_time,
                    "messages": []
                }

            chats_map[chat_ref]["last_message"] = text
            chats_map[chat_ref]["last_time"] = display_time

            chats_map[chat_ref]["messages"].append({
                "id": str(msg_id),
                "text": text,
                "type": "sent" if from_me == 1 else "received",
                "datetime": display_datetime
            })

        chats = list(chats_map.values())

        return jsonify({
            "ok": True,
            "case_id": case_id,
            "source_table": message_table,
            "chats": chats
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
