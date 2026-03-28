import os
import re
import json
from collections import Counter, defaultdict
from datetime import datetime


URL_REGEX = re.compile(r'https?://[^\s]+', re.IGNORECASE)
PHONE_REGEX = re.compile(r'(?<!\d)(?:\+?\d[\d\s\-]{7,}\d)(?!\d)')
OTP_REGEX = re.compile(r'(?<!\d)\d{4,8}(?!\d)')


KEYWORDS = [
    "otp", "code", "bank", "transfer", "payment", "iban", "urgent",
    "password", "verification", "login", "confirm", "click", "link",
    "pin", "account", "wallet", "refund", "security", "reset"
]

AR_KEYWORDS = [
    "كود", "رمز", "تحويل", "بنك", "حساب", "تحقق", "تأكيد", "رابط",
    "اضغط", "عاجل", "دفع", "ايبان", "رقم سري", "كلمة المرور", "استرجاع"
]


def analyze_whatsapp_data(messages, case_id):
    try:
        if not messages:
            return {
                "ok": False,
                "error": "No messages to analyze"
            }

        normalized = normalize_messages(messages)

        summary = build_summary(normalized)
        activity = build_activity(normalized)
        urls = extract_urls(normalized)
        numbers = extract_numbers(normalized)
        keywords = extract_keywords(normalized)
        flags = build_flags(urls, numbers, keywords, normalized)

        return {
            "ok": True,
            "case_id": case_id,
            "summary": summary,
            "activity": activity,
            "flags": flags,
            "urls": urls,
            "numbers": numbers,
            "keywords": keywords,
            "generated_at": datetime.now().isoformat(timespec="seconds")
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


def normalize_messages(messages):
    normalized = []

    for i, msg in enumerate(messages, start=1):
        text = (
            msg.get("text")
            or msg.get("message")
            or msg.get("message_text")
            or ""
        ).strip()

        dt_str = (
            msg.get("datetime")
            or msg.get("date")
            or ""
        ).strip()

        parsed_dt = parse_datetime(dt_str)

        from_me = msg.get("from_me", None)
        msg_type = msg.get("type", "").strip().lower()

        if isinstance(from_me, bool):
            is_sent = from_me
        elif msg_type == "sent":
            is_sent = True
        else:
            is_sent = False

        normalized.append({
            "id": msg.get("id", i),
            "text": text,
            "datetime": dt_str,
            "dt_obj": parsed_dt,
            "from_me": is_sent,
            "contact_name": msg.get("contact_name", ""),
            "remote_jid": msg.get("remote_jid", ""),
        })

    return normalized


def parse_datetime(value):
    if not value:
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass

    return None


def build_summary(messages):
    total = len(messages)
    sent = sum(1 for m in messages if m["from_me"])
    received = total - sent

    datetimes = [m["dt_obj"] for m in messages if m["dt_obj"] is not None]
    datetimes.sort()

    first_contact = datetimes[0].strftime("%Y-%m-%d %H:%M:%S") if datetimes else "-"
    last_contact = datetimes[-1].strftime("%Y-%m-%d %H:%M:%S") if datetimes else "-"

    urls = extract_urls(messages)
    numbers = extract_numbers(messages)
    keywords = extract_keywords(messages)

    return {
        "total_messages": total,
        "sent": sent,
        "received": received,
        "first_contact": first_contact,
        "last_contact": last_contact,
        "urls_count": len(urls),
        "numbers_count": len(numbers),
        "keyword_hits_total": sum(k["hits"] for k in keywords)
    }


def build_activity(messages):
    datetimes = [m["dt_obj"] for m in messages if m["dt_obj"] is not None]

    if not datetimes:
        return []

    hour_counter = Counter()
    day_counter = Counter()

    for dt_obj in datetimes:
        hour_counter[dt_obj.strftime("%H:00")] += 1
        day_counter[dt_obj.strftime("%Y-%m-%d")] += 1

    peak_hour, _ = hour_counter.most_common(1)[0]
    peak_day, _ = day_counter.most_common(1)[0]

    start_dt = min(datetimes)
    end_dt = max(datetimes)
    duration_days = (end_dt.date() - start_dt.date()).days + 1

    sent = sum(1 for m in messages if m["from_me"])
    received = len(messages) - sent

    total = len(messages) if messages else 1
    sent_ratio = round((sent / total) * 100)
    recv_ratio = round((received / total) * 100)

    return [
        {
            "id": "peak_hour",
            "value": peak_hour,
            "value_ar": peak_hour,
            "value_en": peak_hour
        },
        {
            "id": "peak_day",
            "value": peak_day,
            "value_ar": peak_day,
            "value_en": peak_day
        },
        {
            "id": "duration",
            "value": f"{duration_days} days",
            "value_ar": f"{duration_days} يوم",
            "value_en": f"{duration_days} days"
        },
        {
            "id": "ratio",
            "value": f"{sent_ratio}% / {recv_ratio}%",
            "value_ar": f"{sent_ratio}% / {recv_ratio}%",
            "value_en": f"{sent_ratio}% / {recv_ratio}%"
        }
    ]


def extract_urls(messages):
    counter = Counter()

    for msg in messages:
        text = msg["text"]
        found = URL_REGEX.findall(text)
        for u in found:
            counter[u] += 1

    return [
        {"url": url, "count": count}
        for url, count in counter.most_common(20)
    ]


def extract_numbers(messages):
    number_map = {}

    for msg in messages:
        text = msg["text"]

        phones = PHONE_REGEX.findall(text)
        otps = OTP_REGEX.findall(text)

        for p in phones:
            value = clean_number(p)
            if len(value) < 5:
                continue

            if value not in number_map:
                number_map[value] = {
                    "value": value,
                    "context": "Number mentioned in message",
                    "context_ar": "رقم مذكور داخل رسالة",
                    "context_en": "Number mentioned in message",
                    "count": 0
                }
            number_map[value]["count"] += 1

        for o in otps:
            if o not in number_map:
                number_map[o] = {
                    "value": o,
                    "context": "Possible OTP/code",
                    "context_ar": "كود أو OTP محتمل",
                    "context_en": "Possible OTP/code",
                    "count": 0
                }
            number_map[o]["count"] += 1

    items = list(number_map.values())
    items.sort(key=lambda x: x["count"], reverse=True)
    return items[:20]


def clean_number(value):
    return re.sub(r"[^\d+]", "", value).strip()


def extract_keywords(messages):
    hits = defaultdict(lambda: {"hits": 0, "examples": []})

    all_keywords = KEYWORDS + AR_KEYWORDS

    for msg in messages:
        text = msg["text"]
        lower_text = text.lower()

        for kw in all_keywords:
            kw_lower = kw.lower()
            if kw_lower in lower_text:
                hits[kw]["hits"] += 1
                if len(hits[kw]["examples"]) < 3:
                    hits[kw]["examples"].append(text[:120])

    results = []
    for kw, data in hits.items():
        results.append({
            "keyword": kw,
            "hits": data["hits"],
            "examples": data["examples"],
            "examples_ar": data["examples"],
            "examples_en": data["examples"]
        })

    results.sort(key=lambda x: x["hits"], reverse=True)
    return results[:20]


def build_flags(urls, numbers, keywords, messages):
    flags = []

    shorteners = ("bit.ly", "tinyurl", "t.co", "goo.gl", "is.gd", "cutt.ly")
    suspicious_url = any(
        any(short in item["url"].lower() for short in shorteners)
        for item in urls
    )

    if suspicious_url:
        flags.append({
            "level": "warn",
            "title": "Shortened links detected",
            "title_ar": "وجود روابط مختصرة",
            "title_en": "Shortened links detected",
            "description": "Short URLs were found and may require verification.",
            "desc": "Short URLs were found and may require verification.",
            "desc_ar": "تم رصد روابط مختصرة وتحتاج تحقق.",
            "desc_en": "Short URLs were found and may require verification."
        })

    danger_words = {"otp", "bank", "transfer", "code", "verification", "تحويل", "بنك", "كود", "تحقق"}
    keyword_set = {k["keyword"].lower() for k in keywords}
    if keyword_set.intersection({w.lower() for w in danger_words}):
        flags.append({
            "level": "danger",
            "title": "Sensitive keywords detected",
            "title_ar": "كلمات حساسة مرتبطة بالتحويل أو التحقق",
            "title_en": "Sensitive keywords detected",
            "description": "Potentially sensitive banking, verification, or OTP terms were found.",
            "desc": "Potentially sensitive banking, verification, or OTP terms were found.",
            "desc_ar": "تم رصد كلمات حساسة مثل كود أو بنك أو تحويل.",
            "desc_en": "Potentially sensitive banking, verification, or OTP terms were found."
        })

    if numbers:
        flags.append({
            "level": "ok",
            "title": "Numbers/codes extracted",
            "title_ar": "تم استخراج أرقام وأكواد",
            "title_en": "Numbers/codes extracted",
            "description": "The analysis extracted phone numbers or possible codes from the messages.",
            "desc": "The analysis extracted phone numbers or possible codes from the messages.",
            "desc_ar": "التحليل استخرج أرقام أو أكواد محتملة من الرسائل.",
            "desc_en": "The analysis extracted phone numbers or possible codes from the messages."
        })

    if not flags:
        flags.append({
            "level": "ok",
            "title": "No major indicators",
            "title_ar": "لا توجد مؤشرات قوية",
            "title_en": "No major indicators",
            "description": "No major suspicious indicators were found in the current message set.",
            "desc": "No major suspicious indicators were found in the current message set.",
            "desc_ar": "لم يتم العثور على مؤشرات مشبوهة قوية في الرسائل الحالية.",
            "desc_en": "No major suspicious indicators were found in the current message set."
        })

    return flags


def save_analysis_report(analysis_result, case_id, base_cases_dir="Cases"):
    case_dir = os.path.join(base_cases_dir, case_id)
    analysis_dir = os.path.join(case_dir, "Analysis")
    os.makedirs(analysis_dir, exist_ok=True)

    report_path = os.path.join(analysis_dir, "analysis_report.json")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)

    return report_path