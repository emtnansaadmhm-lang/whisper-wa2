import os
import sqlite3
from flask import Blueprint, jsonify

from parser import parse_whatsapp_db, group_messages_by_chat

messages_api = Blueprint("messages_api", __name__)

BASE_DIR = os.path.dirname(__file__)


@messages_api.route("/api/messages/<case_id>", methods=["GET"])
def get_messages(case_id):
    parsed = parse_whatsapp_db(case_id)

    if not parsed.get("ok"):
        return jsonify(parsed), 400

    messages = parsed.get("messages", [])
    grouped = group_messages_by_chat(messages)

    chats = []

    for chat_jid, chat_messages in grouped.items():
        if not chat_messages:
            continue

        first_msg = chat_messages[0]
        last_msg = chat_messages[-1]

        chat_number = first_msg.get("contact_name") or first_msg.get("user") or chat_jid

        formatted_messages = []

        for msg in chat_messages:
            dt_value = msg.get("datetime") or ""
            time_only = ""

            if " " in dt_value:
                time_only = dt_value.split(" ")[1][:5]

            formatted_messages.append({
                "id": str(msg.get("id") or ""),
                "text": msg.get("text") or msg.get("caption") or "",
                "type": "sent" if msg.get("from_me") else "received",
                "datetime": dt_value,
                "user": msg.get("user") or chat_number,

                # Media support
                "media_type": msg.get("media_type"),
                "media_mime": msg.get("media_mime"),
                "media_name": msg.get("media_name"),
                "media_path": msg.get("media_path"),
                "media_url": msg.get("media_url"),
                "caption": msg.get("caption")
            })

        last_text = last_msg.get("text") or last_msg.get("caption") or ""

        if not last_text and last_msg.get("media_type") == "image":
            last_text = "Image"
        elif not last_text and last_msg.get("media_type") == "video":
            last_text = "Video"
        elif not last_text and last_msg.get("media_type") in ["audio", "audio_recorded"]:
            last_text = "Audio"
        elif not last_text and last_msg.get("media_type") == "document":
            last_text = "Document"

        last_datetime = last_msg.get("datetime") or ""
        last_time = last_datetime.split(" ")[1][:5] if " " in last_datetime else ""

        chats.append({
            "id": str(chat_jid),
            "number": chat_number,
            "name": chat_number,
            "last_message": last_text,
            "last_time": last_time,
            "messages": formatted_messages
        })

    return jsonify({
        "ok": True,
        "case_id": case_id,
        "source_table": "message",
        "chats": chats
    }), 200