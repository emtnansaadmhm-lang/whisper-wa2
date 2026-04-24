import os
import sqlite3
from flask import Blueprint, jsonify

messages_api = Blueprint("messages_api", __name__)

BASE_DIR = os.path.dirname(__file__)


def get_db_path(case_id: str) -> str:
    return os.path.join(BASE_DIR, "Cases", case_id, "Decrypted", "msgstore_decrypted.db")


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

    if value == "status@broadcast":
        return "Status"

    if "@s.whatsapp.net" in value:
        return value.split("@")[0]

    if "@lid" in value:
        return value.split("@")[0]

    if "@g.us" in value:
        return value.split("@")[0]

    import re
    match = re.search(r"\d{8,15}", value)
    if match:
        return match.group(0)

    return value


def make_jid_value(row):
    raw = row["raw_string"] if "raw_string" in row.keys() else None
    user = row["user"] if "user" in row.keys() else None
    server = row["server"] if "server" in row.keys() else None

    if raw:
        return raw
    if user and server:
        return f"{user}@{server}"
    if user:
        return str(user)
    return None


def is_lid(value):
    return "@lid" in str(value or "")


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

        message_table = pick_first_existing(tables, ["message", "messages", "chat_messages"])

        if not message_table:
            conn.close()
            return jsonify({
                "ok": False,
                "error": "Could not find a messages table in decrypted DB",
                "tables": tables
            }), 400

        cols = get_columns(cur, message_table)

        id_col = "_id" if "_id" in cols else ("id" if "id" in cols else None)
        key_id_col = "key_id" if "key_id" in cols else None
        chat_col = "chat_row_id" if "chat_row_id" in cols else None
        sender_jid_col = "sender_jid_row_id" if "sender_jid_row_id" in cols else None
        text_col = "text_data" if "text_data" in cols else ("data" if "data" in cols else None)
        ts_col = "timestamp" if "timestamp" in cols else None
        from_me_col = "from_me" if "from_me" in cols else None

        if not text_col:
            conn.close()
            return jsonify({
                "ok": False,
                "error": f"Could not find text column in table {message_table}",
                "table": message_table,
                "columns": cols
            }), 400

        selected_cols = [
            f"{id_col} AS row_id" if id_col else "NULL AS row_id",
            f"{key_id_col} AS key_id" if key_id_col else "NULL AS key_id",
            f"{chat_col} AS chat_ref" if chat_col else "NULL AS chat_ref",
            f"{sender_jid_col} AS sender_jid_ref" if sender_jid_col else "NULL AS sender_jid_ref",
            f"{text_col} AS msg_text",
            f"{ts_col} AS msg_ts" if ts_col else "NULL AS msg_ts",
            f"{from_me_col} AS from_me" if from_me_col else "0 AS from_me"
        ]

        query = f"""
            SELECT {", ".join(selected_cols)}
            FROM {message_table}
            WHERE {text_col} IS NOT NULL AND TRIM({text_col}) != ''
            ORDER BY {ts_col if ts_col else (id_col if id_col else 'rowid')} ASC
            LIMIT 1000
        """

        cur.execute(query)
        rows = cur.fetchall()

        jid_by_id = {}

        if "jid" in tables:
            cur.execute("SELECT _id, user, server, raw_string FROM jid")
            for r in cur.fetchall():
                jid_by_id[str(r["_id"])] = make_jid_value(r)

        # أهم حل: تحويل @lid إلى رقم جوال من jid_map
        if "jid_map" in tables and "jid" in tables:
            cur.execute("""
                SELECT
                    jm.lid_row_id AS lid_id,
                    j.user AS user,
                    j.server AS server,
                    j.raw_string AS raw_string
                FROM jid_map jm
                JOIN jid j ON jm.jid_row_id = j._id
            """)
            for r in cur.fetchall():
                real_phone_jid = make_jid_value(r)
                if real_phone_jid:
                    jid_by_id[str(r["lid_id"])] = real_phone_jid

        chat_number_by_id = {}

        if "chat" in tables:
            chat_cols = get_columns(cur, "chat")

            if "_id" in chat_cols and "jid_row_id" in chat_cols:
                cur.execute("SELECT _id, jid_row_id FROM chat")
                for r in cur.fetchall():
                    chat_id = str(r["_id"])
                    jid_id = str(r["jid_row_id"])
                    chat_number_by_id[chat_id] = jid_by_id.get(jid_id, jid_id)

            if "subject" in chat_cols:
                cur.execute("""
                    SELECT _id, subject
                    FROM chat
                    WHERE subject IS NOT NULL AND TRIM(subject) != ''
                """)
                for r in cur.fetchall():
                    chat_id = str(r["_id"])
                    if chat_id not in chat_number_by_id:
                        chat_number_by_id[chat_id] = r["subject"]

        conn.close()

        chats_map = {}

        for row in rows:
            row = dict(row)

            chat_ref = str(row.get("chat_ref")) if row.get("chat_ref") is not None else "unknown_chat"
            sender_jid_ref = row.get("sender_jid_ref")

            msg_id = row.get("key_id") or row.get("row_id") or ""
            text = row.get("msg_text") or ""
            timestamp = row.get("msg_ts")
            from_me = int(row.get("from_me") or 0)

            chat_jid = chat_number_by_id.get(chat_ref, chat_ref)
            chat_number = clean_number(chat_jid)

            if is_lid(chat_jid):
                mapped = jid_by_id.get(str(sender_jid_ref))
                if mapped:
                    chat_number = clean_number(mapped)

            sender_jid = jid_by_id.get(str(sender_jid_ref)) if sender_jid_ref else None

            if from_me == 0 and sender_jid:
                message_user = clean_number(sender_jid)
            else:
                message_user = chat_number

            display_time = ""
            display_datetime = ""

            try:
                if timestamp is not None:
                    ts = int(timestamp)
                    import datetime as dt

                    if ts > 10_000_000_000:
                        dt_obj = dt.datetime.fromtimestamp(ts / 1000)
                    else:
                        dt_obj = dt.datetime.fromtimestamp(ts)

                    display_time = dt_obj.strftime("%H:%M")
                    display_datetime = dt_obj.strftime("%Y-%m-%d %H:%M")
            except Exception:
                display_time = ""
                display_datetime = str(timestamp or "")

            if chat_ref not in chats_map:
                chats_map[chat_ref] = {
                    "id": chat_ref,
                    "number": chat_number,
                    "name": chat_number,
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
                "datetime": display_datetime,
                "user": message_user
            })

        return jsonify({
            "ok": True,
            "case_id": case_id,
            "source_table": message_table,
            "chats": list(chats_map.values())
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
