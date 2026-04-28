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
        return {"ok": False, "error": f"Database file not found: {db_path}"}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        tables = get_tables(cursor)
        message_table = pick_first_existing(tables, ["message", "messages", "chat_messages"])

        if not message_table:
            conn.close()
            return {
                "ok": False,
                "error": "Could not find a messages table in decrypted DB",
                "tables": tables
            }

        messages = extract_messages(cursor, message_table, tables, case_id)
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
        return {"ok": False, "error": f"SQLite error: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {str(e)}"}


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


def first_existing_col(cols, candidates):
    for c in candidates:
        if c in cols:
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
        selected_cols.append("user" if "user" in jid_cols else "NULL AS user")
        selected_cols.append("server" if "server" in jid_cols else "NULL AS server")
        selected_cols.append("raw_string" if "raw_string" in jid_cols else "NULL AS raw_string")

        cursor.execute(f"SELECT {', '.join(selected_cols)} FROM jid")

        for r in cursor.fetchall():
            value = make_jid_value(r)
            if value:
                jid_by_id[str(r["_id"])] = value

    # تحويل LID إلى الرقم الحقيقي
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


def normalize_media_path(path_value):
    if not path_value:
        return None

    path_value = str(path_value).strip().replace("\\", "/")
    if not path_value:
        return None

    markers = [
        "WhatsApp/Media/",
        "Media/Media/",
        "Media/"
    ]

    for marker in markers:
        if marker in path_value:
            return path_value.split(marker, 1)[1].lstrip("/")

    return os.path.basename(path_value)


def get_default_media_folder(media_type):
    folders = {
        "image": "WhatsApp Images",
        "video": "WhatsApp Video",
        "audio": "WhatsApp Audio",
        "audio_recorded": "WhatsApp Voice Notes",
        "document": "WhatsApp Documents",
        "gif": "WhatsApp Animated Gifs",
        "sticker": "WhatsApp Stickers"
    }
    return folders.get(media_type)


def find_media_file(case_id, media_type_name, media_name):
    if not media_name:
        return None

    media_name = str(media_name).strip()
    if not media_name:
        return None

    search_roots = [
        os.path.join("Cases", case_id, "Evidence", "Media", "Media"),
        os.path.join("Cases", case_id, "Evidence", "Media")
    ]

    folders = {
        "image": [
            "WhatsApp Images",
            os.path.join("WhatsApp Images", "Sent")
        ],
        "video": [
            "WhatsApp Video",
            os.path.join("WhatsApp Video", "Sent")
        ],
        "audio": [
            "WhatsApp Audio",
            "WhatsApp Voice Notes",
            os.path.join("WhatsApp Audio", "Sent"),
            os.path.join("WhatsApp Voice Notes", "Sent")
        ],
        "audio_recorded": [
            "WhatsApp Voice Notes",
            "WhatsApp Audio",
            os.path.join("WhatsApp Voice Notes", "Sent"),
            os.path.join("WhatsApp Audio", "Sent")
        ],
        "document": [
            "WhatsApp Documents",
            os.path.join("WhatsApp Documents", "Sent")
        ],
        "gif": [
            "WhatsApp Animated Gifs",
            os.path.join("WhatsApp Animated Gifs", "Sent")
        ],
        "sticker": [
            "WhatsApp Stickers",
            os.path.join("WhatsApp Stickers", "Sent")
        ]
    }

    possible_folders = folders.get(media_type_name, [])
    media_no_ext = os.path.splitext(media_name)[0]

    for root in search_roots:
        for folder in possible_folders:
            folder_path = os.path.join(root, folder)

            if not os.path.exists(folder_path):
                continue

            for file in os.listdir(folder_path):
                file_no_ext = os.path.splitext(file)[0]

                if file == media_name or file_no_ext == media_no_ext:
                    return os.path.join(folder, file).replace("\\", "/")

    return None


def build_media_url(case_id, media_relative_path):
    if not media_relative_path:
        return None

    safe_path = str(media_relative_path).replace("\\", "/").lstrip("/")
    return f"/api/media/{case_id}/{safe_path}"


def get_media_type_from_mime(mime_type):
    if not mime_type:
        return None

    mime_type = str(mime_type).lower()

    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    if "pdf" in mime_type or "document" in mime_type or "word" in mime_type or "excel" in mime_type:
        return "document"

    return None


def get_media_type_name(media_type):
    try:
        media_type = int(media_type) if media_type is not None else 0
    except Exception:
        media_type = 0

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


def extract_messages(cursor: sqlite3.Cursor, table_name: str, tables, case_id: str):
    cols = get_columns(cursor, table_name)

    id_col = "_id" if "_id" in cols else ("id" if "id" in cols else None)

    chat_col = first_existing_col(cols, ["chat_row_id", "key_remote_jid", "remote_jid", "jid"])
    sender_jid_col = "sender_jid_row_id" if "sender_jid_row_id" in cols else None
    from_me_col = first_existing_col(cols, ["from_me", "key_from_me"])
    text_col = first_existing_col(cols, ["text_data", "data", "body", "message", "content"])
    ts_col = first_existing_col(cols, ["timestamp", "message_date", "sort_timestamp", "received_timestamp", "sent_timestamp"])

    media_type_col = first_existing_col(cols, ["media_wa_type", "media_type"])
    media_mime_col = first_existing_col(cols, ["media_mime_type", "mime_type"])
    caption_col = first_existing_col(cols, ["media_caption", "caption"])

    media_name_col = first_existing_col(cols, [
        "media_name",
        "file_name",
        "filename",
        "media_file_name"
    ])

    media_path_col = first_existing_col(cols, [
        "media_file_path",
        "file_path",
        "media_path",
        "local_path",
        "file_local_path",
        "path"
    ])

    lat_col = "latitude" if "latitude" in cols else None
    lon_col = "longitude" if "longitude" in cols else None

    has_message_media = "message_media" in tables
    mm_cols = get_columns(cursor, "message_media") if has_message_media else []

    mm_join_col = first_existing_col(mm_cols, [
        "message_row_id",
        "message_id",
        "msg_row_id"
    ])

    mm_file_path_col = first_existing_col(mm_cols, [
        "file_path",
        "media_file_path",
        "media_path",
        "local_path",
        "file_local_path",
        "path"
    ])

    mm_file_name_col = first_existing_col(mm_cols, [
        "file_name",
        "media_name",
        "filename",
        "media_file_name"
    ])

    mm_mime_col = first_existing_col(mm_cols, [
        "mime_type",
        "media_mime_type"
    ])

    mm_media_type_col = first_existing_col(mm_cols, [
        "media_type",
        "media_wa_type"
    ])

    mm_caption_col = first_existing_col(mm_cols, [
        "caption",
        "media_caption"
    ])

    selected = []
    selected.append(f"m.{id_col} as msg_id" if id_col else "NULL as msg_id")
    selected.append(f"m.{chat_col} as chat_ref" if chat_col else "NULL as chat_ref")
    selected.append(f"m.{sender_jid_col} as sender_jid_ref" if sender_jid_col else "NULL as sender_jid_ref")
    selected.append(f"m.{from_me_col} as from_me" if from_me_col else "0 as from_me")
    selected.append(f"m.{text_col} as message_text" if text_col else "NULL as message_text")
    selected.append(f"m.{ts_col} as timestamp" if ts_col else "NULL as timestamp")
    selected.append(f"m.{media_type_col} as media_wa_type" if media_type_col else "NULL as media_wa_type")
    selected.append(f"m.{media_mime_col} as media_mime_type" if media_mime_col else "NULL as media_mime_type")
    selected.append(f"m.{caption_col} as media_caption" if caption_col else "NULL as media_caption")
    selected.append(f"m.{media_name_col} as media_name" if media_name_col else "NULL as media_name")
    selected.append(f"m.{media_path_col} as media_file_path" if media_path_col else "NULL as media_file_path")
    selected.append(f"m.{lat_col} as latitude" if lat_col else "NULL as latitude")
    selected.append(f"m.{lon_col} as longitude" if lon_col else "NULL as longitude")

    if has_message_media and mm_join_col and id_col:
        selected.append(f"mm.{mm_file_path_col} as mm_file_path" if mm_file_path_col else "NULL as mm_file_path")
        selected.append(f"mm.{mm_file_name_col} as mm_file_name" if mm_file_name_col else "NULL as mm_file_name")
        selected.append(f"mm.{mm_mime_col} as mm_mime_type" if mm_mime_col else "NULL as mm_mime_type")
        selected.append(f"mm.{mm_media_type_col} as mm_media_type" if mm_media_type_col else "NULL as mm_media_type")
        selected.append(f"mm.{mm_caption_col} as mm_caption" if mm_caption_col else "NULL as mm_caption")

        join_sql = f"""
            LEFT JOIN message_media mm
            ON m.{id_col} = mm.{mm_join_col}
        """
    else:
        selected.append("NULL as mm_file_path")
        selected.append("NULL as mm_file_name")
        selected.append("NULL as mm_mime_type")
        selected.append("NULL as mm_media_type")
        selected.append("NULL as mm_caption")
        join_sql = ""

    order_by = f"m.{ts_col}" if ts_col else (f"m.{id_col}" if id_col else "m.rowid")

    where_parts = []

    if text_col:
        where_parts.append(f"(m.{text_col} IS NOT NULL AND TRIM(m.{text_col}) != '')")

    if media_type_col:
        where_parts.append(f"(m.{media_type_col} IS NOT NULL AND m.{media_type_col} != 0)")

    if caption_col:
        where_parts.append(f"(m.{caption_col} IS NOT NULL AND TRIM(m.{caption_col}) != '')")

    if media_name_col:
        where_parts.append(f"(m.{media_name_col} IS NOT NULL AND TRIM(m.{media_name_col}) != '')")

    if media_path_col:
        where_parts.append(f"(m.{media_path_col} IS NOT NULL AND TRIM(m.{media_path_col}) != '')")

    if has_message_media and mm_join_col:
        if mm_file_path_col:
            where_parts.append(f"(mm.{mm_file_path_col} IS NOT NULL AND TRIM(mm.{mm_file_path_col}) != '')")
        if mm_file_name_col:
            where_parts.append(f"(mm.{mm_file_name_col} IS NOT NULL AND TRIM(mm.{mm_file_name_col}) != '')")
        if mm_mime_col:
            where_parts.append(f"(mm.{mm_mime_col} IS NOT NULL AND TRIM(mm.{mm_mime_col}) != '')")

    where_clause = " OR ".join(where_parts) if where_parts else "1=1"

    query = f"""
        SELECT {", ".join(selected)}
        FROM {table_name} m
        {join_sql}
        WHERE {where_clause}
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

            media_type_raw = row["mm_media_type"] or row["media_wa_type"]
            media_file_path = row["mm_file_path"] or row["media_file_path"]
            media_name = row["mm_file_name"] or row["media_name"]
            media_mime = row["mm_mime_type"] or row["media_mime_type"]

            media_type_name = get_media_type_name(media_type_raw)

            if media_type_name in ["text", "unknown"]:
                mime_type_name = get_media_type_from_mime(media_mime)
                if mime_type_name:
                    media_type_name = mime_type_name

            media_relative_path = normalize_media_path(media_file_path)

            if not media_relative_path and media_name:
                media_relative_path = find_media_file(case_id, media_type_name, media_name)

            if media_relative_path and "/" not in str(media_relative_path) and media_name:
                found_path = find_media_file(case_id, media_type_name, media_name)
                if found_path:
                    media_relative_path = found_path

            if not media_relative_path and media_name:
                media_folder = get_default_media_folder(media_type_name)
                if media_folder:
                    media_relative_path = f"{media_folder}/{media_name}"
                else:
                    media_relative_path = str(media_name)

            media_url = build_media_url(case_id, media_relative_path)

            text_value = row["message_text"] or ""
            caption_value = row["mm_caption"] or row["media_caption"] or ""

            msg = {
                "id": row["msg_id"],
                "remote_jid": str(chat_jid),
                "from_me": from_me,
                "text": text_value,
                "timestamp": row["timestamp"],
                "datetime": timestamp_to_datetime(row["timestamp"]),
                "media_type": media_type_name,
                "media_mime": media_mime,
                "media_name": media_name,
                "media_path": media_relative_path,
                "media_url": media_url,
                "caption": caption_value,
                "latitude": row["latitude"],
                "longitude": row["longitude"],
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
