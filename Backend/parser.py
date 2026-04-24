"""
parser.py - WhatsApp Database Parser
Extract messages from decrypted WhatsApp database
"""

import sqlite3
import os
import re
from datetime import datetime


def parse_whatsapp_db(
    case_id: str,
    base_cases_dir: str = "Cases",
    db_filename: str = "msgstore_decrypted.db"
) -> dict:
    case_dir = os.path.join(base_cases_dir, case_id)
    decrypted_dir = os.path.join(case_dir, "Decrypted")
    db_path = os.path.join(decrypted_dir, db_filename)

    if not os.path.exists(db_path):
        return {
            "ok": False,
            "error": f"Database file not found: {db_path}"
        }

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        tables = get_tables(cursor)

        message_table = pick_first_existing(tables, [
            "message",
            "messages",
            "chat_messages"
        ])

        if not message_table:
            conn.close()
            return {
                "ok": False,
                "error": "Could not find a messages table in decrypted DB",
                "tables": tables
            }

        messages = extract_messages(cursor, message_table, tables)
        contacts = extract_contacts(cursor, tables)

        conn.close()

        messages_with_contacts = enrich_messages_with_contacts(messages, contacts)

        return {
            "ok": True,
            "case_id": case_id,
            "total_messages": len(messages_with_contacts),
            "messages": messages_with_contacts,
            "contacts": contacts,
            "extracted_at": datetime.now().isoformat()
        }

    except sqlite3.Error as e:
        return {
            "ok": False,
            "error": f"SQLite error: {str(e)}"
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Unexpected error: {str(e)}"
        }


def get_tables(cursor):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cursor.fetchall()]


def get_columns(cursor, table_name: str):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


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

    value = value.replace("@s.whatsapp.net", "")
    value = value.replace("@g.us", "")
    value = value.replace("@lid", "")

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


def build_jid_maps(cursor, tables):
    jid_by_id = {}

    if "jid" in tables:
        jid_cols = get_columns(cursor, "jid")

        selected_cols = ["_id"]

        if "user" in jid_cols:
            selected_cols.append("user")
        else:
            selected_cols.append("NULL AS user")

        if "server" in jid_cols:
            selected_cols.append("server")
        else:
            selected_cols.append("NULL AS server")

        if "raw_string" in jid_cols:
            selected_cols.append("raw_string")
        else:
            selected_cols.append("NULL AS raw_string")

        cursor.execute(f"SELECT {', '.join(selected_cols)} FROM jid")

        for r in cursor.fetchall():
            value = make_jid_value(r)
            if value:
                jid_by_id[str(r["_id"])] = value

    # تحويل LID إلى رقم واتساب الحقيقي من jid_map
    if "jid_map" in tables and "jid" in tables:
        try:
            cursor.execute("""
                SELECT
                    jm.lid_row_id AS lid_id,
                    j.user AS user,
                    j.server AS server,
                    j.raw_string AS raw_string
                FROM jid_map jm
                JOIN jid j ON jm.jid_row_id = j._id
            """)

            for r in cursor.fetchall():
                real_value = make_jid_value(r)
                if real_value:
                    jid_by_id[str(r["lid_id"])] = real_value

        except sqlite3.Error:
            pass

    return jid_by_id


def build_chat_map(cursor, tables, jid_by_id):
    chat_by_id = {}

    if "chat" not in tables:
        return chat_by_id

    chat_cols = get_columns(cursor, "chat")

    if "_id" in chat_cols and "jid_row_id" in chat_cols:
        cursor.execute("SELECT _id, jid_row_id FROM chat")
        for r in cursor.fetchall():
            chat_id = str(r["_id"])
            jid_id = str(r["jid_row_id"])
            chat_by_id[chat_id] = jid_by_id.get(jid_id, jid_id)

    if "_id" in chat_cols and "subject" in chat_cols:
        cursor.execute("""
            SELECT _id, subject
            FROM chat
            WHERE subject IS NOT NULL AND TRIM(subject) != ''
        """)
        for r in cursor.fetchall():
            chat_id = str(r["_id"])
            if chat_id not in chat_by_id:
                chat_by_id[chat_id] = r["subject"]

    return chat_by_id


def extract_messages(cursor: sqlite3.Cursor, table_name: str, tables):
    cols = get_columns(cursor, table_name)

    id_col = "_id" if "_id" in cols else ("id" if "id" in cols else None)

    chat_col = None
    for c in ["chat_row_id", "key_remote_jid", "remote_jid", "jid"]:
        if c in cols:
            chat_col = c
            break

    sender_jid_col = "sender_jid_row_id" if "sender_jid_row_id" in cols else None

    from_me_col = None
    for c in ["from_me", "key_from_me"]:
        if c in cols:
            from_me_col = c
            break

    text_col = None
    for c in ["text_data", "data", "body", "message", "content"]:
        if c in cols:
            text_col = c
            break

    ts_col = None
    for c in ["timestamp", "message_date", "sort_timestamp", "received_timestamp", "sent_timestamp"]:
        if c in cols:
            ts_col = c
            break

    media_type_col = "media_wa_type" if "media_wa_type" in cols else None
    media_mime_col = "media_mime_type" if "media_mime_type" in cols else None
    caption_col = "media_caption" if "media_caption" in cols else None
    lat_col = "latitude" if "latitude" in cols else None
    lon_col = "longitude" if "longitude" in cols else None

    if not text_col:
        return []

    selected = []
    selected.append(f"{id_col} as msg_id" if id_col else "NULL as msg_id")
    selected.append(f"{chat_col} as chat_ref" if chat_col else "NULL as chat_ref")
    selected.append(f"{sender_jid_col} as sender_jid_ref" if sender_jid_col else "NULL as sender_jid_ref")
    selected.append(f"{from_me_col} as from_me" if from_me_col else "0 as from_me")
    selected.append(f"{text_col} as message_text")
    selected.append(f"{ts_col} as timestamp" if ts_col else "NULL as timestamp")
    selected.append(f"{media_type_col} as media_wa_type" if media_type_col else "NULL as media_wa_type")
    selected.append(f"{media_mime_col} as media_mime_type" if media_mime_col else "NULL as media_mime_type")
    selected.append(f"{caption_col} as media_caption" if caption_col else "NULL as media_caption")
    selected.append(f"{lat_col} as latitude" if lat_col else "NULL as latitude")
    selected.append(f"{lon_col} as longitude" if lon_col else "NULL as longitude")

    order_by = ts_col if ts_col else (id_col if id_col else "rowid")

    query = f"""
        SELECT {", ".join(selected)}
        FROM {table_name}
        WHERE {text_col} IS NOT NULL AND TRIM({text_col}) != ''
        ORDER BY {order_by} ASC
    """

    try:
        jid_by_id = build_jid_maps(cursor, tables)
        chat_by_id = build_chat_map(cursor, tables, jid_by_id)

        cursor.execute(query)
        rows = cursor.fetchall()

        messages = []

        for row in rows:
            chat_ref = str(row["chat_ref"]) if row["chat_ref"] is not None else "unknown"
            sender_jid_ref = str(row["sender_jid_ref"]) if row["sender_jid_ref"] is not None else None
            from_me = bool(row["from_me"])

            chat_jid = chat_by_id.get(chat_ref, chat_ref)
            chat_number = clean_number(chat_jid)

            sender_jid = jid_by_id.get(sender_jid_ref) if sender_jid_ref else None

            if not from_me and sender_jid:
                user_number = clean_number(sender_jid)
            else:
                user_number = chat_number

            msg = {
                "id": row["msg_id"],
                "remote_jid": str(chat_jid),
                "from_me": from_me,
                "text": row["message_text"] or "",
                "timestamp": row["timestamp"],
                "datetime": timestamp_to_datetime(row["timestamp"]),
                "media_type": get_media_type_name(row["media_wa_type"]),
                "media_mime": row["media_mime_type"],
                "caption": row["media_caption"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],

                # هذا المهم للتحليل Activity Pattern
                "user": user_number,
                "contact_name": user_number
            }

            messages.append(msg)

        return messages

    except sqlite3.Error as e:
        print(f"Error extracting messages: {e}")
        return []


def extract_contacts(cursor: sqlite3.Cursor, tables):
    contacts = {}

    if "wa_contacts" in tables:
        try:
            cursor.execute("""
                SELECT jid, display_name, given_name, status
                FROM wa_contacts
                WHERE jid IS NOT NULL
            """)
            rows = cursor.fetchall()

            for row in rows:
                jid = row["jid"]
                contacts[jid] = {
                    "display_name": row["display_name"] or "Unknown",
                    "given_name": "",
                    "status": row["status"] or ""
                }

            return contacts
        except sqlite3.Error as e:
            print(f"Error extracting wa_contacts: {e}")

    if "jid" in tables:
        try:
            jid_cols = get_columns(cursor, "jid")

            if "raw_string" in jid_cols:
                cursor.execute("SELECT _id, raw_string FROM jid")
                rows = cursor.fetchall()
                for row in rows:
                    value = row["raw_string"] or "Unknown"
                    contacts[str(row["_id"])] = {
                        "display_name": value,
                        "given_name": "",
                        "status": ""
                    }

            elif "user" in jid_cols:
                cursor.execute("SELECT _id, user FROM jid")
                rows = cursor.fetchall()
                for row in rows:
                    value = row["user"] or "Unknown"
                    contacts[str(row["_id"])] = {
                        "display_name": value,
                        "given_name": "",
                        "status": ""
                    }

        except sqlite3.Error as e:
            print(f"Error extracting jid contacts: {e}")

    return contacts


def enrich_messages_with_contacts(messages, contacts):
    for msg in messages:
        jid = str(msg.get("remote_jid", ""))

        # لا نغطي الرقم الصحيح اللي طلعناه
        if msg.get("user"):
            msg["contact_name"] = msg["user"]
            msg["contact_status"] = ""
            continue

        if jid in contacts:
            msg["contact_name"] = contacts[jid]["display_name"]
            msg["contact_status"] = contacts[jid]["status"]
        else:
            phone = jid.split("@")[0] if "@" in jid else jid
            msg["contact_name"] = phone
            msg["contact_status"] = ""

    return messages


def timestamp_to_datetime(timestamp):
    if timestamp:
        try:
            ts = int(timestamp)
            if ts > 10_000_000_000:
                dt = datetime.fromtimestamp(ts / 1000.0)
            else:
                dt = datetime.fromtimestamp(ts)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""
    return ""


def get_media_type_name(media_type):
    media_types = {
        0: "text",
        1: "image",
        2: "audio",
        3: "video",
        4: "contact",
        5: "location",
        9: "document",
        13: "gif",
        15: "audio_recorded",
        16: "sticker"
    }
    return media_types.get(media_type, "unknown")


def format_phone_number(phone: str):
    if phone.startswith("966"):
        phone = "0" + phone[3:]

    if len(phone) >= 10:
        return phone[:3] + "XXXX" + phone[-3:]

    return phone


def group_messages_by_chat(messages):
    chats = {}

    for msg in messages:
        jid = msg["remote_jid"]
        if jid not in chats:
            chats[jid] = []
        chats[jid].append(msg)

    return chats


def get_chat_summary(messages):
    if not messages:
        return {}

    sent_count = sum(1 for m in messages if m["from_me"])
    received_count = len(messages) - sent_count

    return {
        "total_messages": len(messages),
        "sent": sent_count,
        "received": received_count,
        "first_message": messages[0]["datetime"],
        "last_message": messages[-1]["datetime"],
        "contact_name": messages[0].get("contact_name", "Unknown")
    }
