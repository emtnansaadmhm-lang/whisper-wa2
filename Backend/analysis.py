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

VERIFICATION_TERMS = {
    "otp", "code", "verification", "verify", "login", "account", "password",
    "pin", "confirm", "security", "reset",
    "كود", "رمز", "تحقق", "تأكيد", "حساب", "رقم سري", "كلمة المرور", "استرجاع"
}

FINANCIAL_TERMS = {
    "bank", "transfer", "payment", "wallet", "refund", "iban",
    "بنك", "تحويل", "دفع", "ايبان"
}

URGENT_TERMS = {
    "urgent", "immediately", "now", "asap", "quick", "click",
    "عاجل", "الآن", "فوراً", "اضغط"
}


def analyze_whatsapp_data(messages, case_id):
    try:
        if not messages:
            return {"ok": False, "error": "No messages to analyze"}

        normalized = normalize_messages(messages)

        summary = build_summary(normalized)
        activity = build_activity(normalized)
        urls = extract_urls(normalized)
        numbers = extract_numbers(normalized)
        keywords = extract_keywords(normalized)
        flags = build_flags(urls, numbers, keywords, normalized)
        flow = detect_suspicious_flow(normalized, urls, numbers, keywords)
        top_suspicious_message = get_top_suspicious_message(normalized)
        recommendations = build_recommendations(
            urls, numbers, keywords, normalized, flow, top_suspicious_message
        )

        return {
            "ok": True,
            "case_id": case_id,
            "summary": summary,
            "activity": activity,
            "flags": flags,
            "flow": flow,
            "top_suspicious_message": top_suspicious_message,
            "recommendations": recommendations,
            "urls": urls,
            "numbers": numbers,
            "keywords": keywords,
            "generated_at": datetime.now().isoformat(timespec="seconds")
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


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

            # مهم: هذا الرقم الصحيح القادم من messages_api
            "user": msg.get("user", ""),

            # fallback فقط
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
    non_saudi_count = sum(1 for n in numbers if n.get("is_non_saudi"))

    return {
        "total_messages": total,
        "sent": sent,
        "received": received,
        "first_contact": first_contact,
        "last_contact": last_contact,
        "urls_count": len(urls),
        "numbers_count": len(numbers),
        "non_saudi_numbers_count": non_saudi_count,
        "keyword_hits_total": sum(k["hits"] for k in keywords)
    }


def clean_contact_label(value):
    value = (value or "").strip()
    if not value:
        return "Unknown"

    if value == "status@broadcast":
        return "Status"

    value = value.replace("@s.whatsapp.net", "")
    value = value.replace("@g.us", "")
    value = value.replace("@lid", "")

    match = re.search(r"\d{8,15}", value)
    if match:
        return match.group(0)

    return value


def is_internal_weird_label(value):
    value = str(value or "").strip()
    return value.isdigit() and len(value) > 15


def get_contact_label(msg):
    user_raw = (msg.get("user", "") or "").strip()
    contact_name_raw = (msg.get("contact_name", "") or "").strip()
    remote_jid_raw = (msg.get("remote_jid", "") or "").strip()

    user_clean = clean_contact_label(user_raw)
    contact_name = clean_contact_label(contact_name_raw)
    remote_jid = clean_contact_label(remote_jid_raw)

    # الأولوية للرقم الحقيقي القادم من messages_api
    if user_clean and user_clean != "Unknown" and not is_internal_weird_label(user_clean):
        return user_clean

    if re.fullmatch(r"\d{8,15}", contact_name) and not is_internal_weird_label(contact_name):
        return contact_name

    if re.fullmatch(r"\d{8,15}", remote_jid) and not is_internal_weird_label(remote_jid):
        return remote_jid

    if contact_name and contact_name != "Unknown" and not is_internal_weird_label(contact_name):
        return contact_name

    if remote_jid and remote_jid != "Unknown" and not is_internal_weird_label(remote_jid):
        return remote_jid

    return "Unknown"


def get_most_contacted(messages):
    counter = Counter()

    for msg in messages:
        label = get_contact_label(msg)
        counter[label] += 1

    if not counter:
        return None

    value, count = counter.most_common(1)[0]
    return {
        "id": "most_contacted",
        "value": value,
        "value_ar": value,
        "value_en": value,
        "count": count
    }


def get_most_active_chat(messages):
    counter = Counter()

    for msg in messages:
        label = get_contact_label(msg)
        counter[label] += 1

    if not counter:
        return None

    value, count = counter.most_common(1)[0]
    return {
        "id": "most_active",
        "value": value,
        "value_ar": value,
        "value_en": value,
        "count": count
    }


def get_most_recent_chat(messages):
    dated_messages = [m for m in messages if m["dt_obj"] is not None]
    if not dated_messages:
        return None

    latest = max(dated_messages, key=lambda x: x["dt_obj"])
    value = get_contact_label(latest)

    return {
        "id": "most_recent",
        "value": value,
        "value_ar": value,
        "value_en": value,
        "datetime": latest.get("datetime") or "-"
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

    activity_items = []

    most_contacted = get_most_contacted(messages)
    if most_contacted:
        activity_items.append(most_contacted)

    most_active = get_most_active_chat(messages)
    if most_active:
        activity_items.append(most_active)

    most_recent = get_most_recent_chat(messages)
    if most_recent:
        activity_items.append(most_recent)

    activity_items.extend([
        {"id": "peak_hour", "value": peak_hour, "value_ar": peak_hour, "value_en": peak_hour},
        {"id": "peak_day", "value": peak_day, "value_ar": peak_day, "value_en": peak_day},
        {"id": "duration", "value": f"{duration_days} days", "value_ar": f"{duration_days} يوم", "value_en": f"{duration_days} days"},
        {"id": "ratio", "value": f"{sent_ratio}% / {recv_ratio}%", "value_ar": f"{sent_ratio}% / {recv_ratio}%", "value_en": f"{sent_ratio}% / {recv_ratio}%"}
    ])

    return activity_items


def extract_urls(messages):
    counter = Counter()

    for msg in messages:
        text = msg["text"]
        found = URL_REGEX.findall(text)
        for u in found:
            counter[u] += 1

    return [{"url": url, "count": count} for url, count in counter.most_common(20)]


def extract_numbers(messages):
    number_map = {}

    for msg in messages:
        text = msg["text"]

        phones = PHONE_REGEX.findall(text)
        otps = OTP_REGEX.findall(text)

        for p in phones:
            value = clean_number(p)
            if len(value) < 7:
                continue

            is_non_saudi = not is_saudi_number(value)

            if value not in number_map:
                number_map[value] = {
            "value": value,
            "type": "foreign_contact" if is_non_saudi else "phone",
            "is_non_saudi": is_non_saudi,
            "context": "Foreign number contacted" if is_non_saudi else "Phone number mentioned in message",
            "context_ar": "رقم أجنبي تم التواصل معه" if is_non_saudi else "رقم هاتف مذكور داخل رسالة",
            "context_en": "Foreign number contacted" if is_non_saudi else "Phone number mentioned in message",
            "count": 0
                }
            number_map[value]["count"] += 1

        for o in otps:
            if len(o) < 4 or len(o) > 8:
                continue

            if o not in number_map:
                number_map[o] = {
                    "value": o,
                    "type": "otp",
                    "context": "Possible OTP or verification code",
                    "context_ar": "كود تحقق أو OTP محتمل",
                    "context_en": "Possible OTP or verification code",
                    "count": 0
                }
            number_map[o]["count"] += 1

    items = list(number_map.values())
    items.sort(key=lambda x: x["count"], reverse=True)
    return items[:20]

def clean_number(value):
    return re.sub(r"[^\d+]", "", value or "").strip()


def normalize_phone_digits(value):
    value = clean_number(value)
    value = value.replace("+", "")

    if value.startswith("00"):
        value = value[2:]

    return value


def is_saudi_number(value):
    digits = normalize_phone_digits(value)
    return digits.startswith("966")


def is_valid_phone_number(value):
    digits = normalize_phone_digits(value)
    return digits.isdigit() and 8 <= len(digits) <= 15

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

    total = len(messages)
    sent = sum(1 for m in messages if m["from_me"])
    received = total - sent

    shorteners = ("bit.ly", "tinyurl", "t.co", "goo.gl", "is.gd", "cutt.ly")
    has_shortened_url = any(
        any(short in item["url"].lower() for short in shorteners)
        for item in urls
    )

    has_external_urls = len(urls) > 0
    has_otp = any(item.get("type") == "otp" for item in numbers)
    has_non_saudi = any(item.get("is_non_saudi") for item in numbers)
    keyword_set = {k["keyword"].lower() for k in keywords}
    has_sensitive_keywords = bool(
        keyword_set.intersection({w.lower() for w in VERIFICATION_TERMS.union(FINANCIAL_TERMS)})
    )

    high_inbound_ratio = False
    if total > 0:
        inbound_ratio = (received / total) * 100
        high_inbound_ratio = inbound_ratio >= 80

    if has_external_urls:
        flags.append({
            "level": "warn",
            "title": "External links detected",
            "title_ar": "تم العثور على روابط خارجية",
            "title_en": "External links detected",
            "description": "One or more external URLs were identified in the conversation.",
            "desc": "One or more external URLs were identified in the conversation.",
            "desc_ar": "تم رصد رابط خارجي واحد أو أكثر داخل المحادثة.",
            "desc_en": "One or more external URLs were identified in the conversation."
        })

    if has_shortened_url:
        flags.append({
            "level": "warn",
            "title": "Shortened links detected",
            "title_ar": "تم العثور على روابط مختصرة",
            "title_en": "Shortened links detected",
            "description": "Shortened URLs may obscure the final destination and require verification.",
            "desc": "Shortened URLs may obscure the final destination and require verification.",
            "desc_ar": "الروابط المختصرة قد تخفي الوجهة النهائية وتحتاج إلى تحقق إضافي.",
            "desc_en": "Shortened URLs may obscure the final destination and require verification."
        })

    if has_otp:
        flags.append({
            "level": "danger",
            "title": "Possible OTP or verification codes detected",
            "title_ar": "تم رصد أكواد تحقق محتملة",
            "title_en": "Possible OTP or verification codes detected",
            "description": "Numeric patterns resembling OTP or verification codes were detected in the messages.",
            "desc": "Numeric patterns resembling OTP or verification codes were detected in the messages.",
            "desc_ar": "تم العثور على أنماط رقمية تشبه أكواد التحقق أو OTP داخل الرسائل.",
            "desc_en": "Numeric patterns resembling OTP or verification codes were detected in the messages."
        })

    if has_sensitive_keywords:
        flags.append({
            "level": "danger",
            "title": "Sensitive verification or banking keywords detected",
            "title_ar": "تم رصد كلمات حساسة مرتبطة بالتحقق أو المعاملات",
            "title_en": "Sensitive verification or banking keywords detected",
            "description": "Terms related to verification, credentials, banking, or account access were identified.",
            "desc": "Terms related to verification, credentials, banking, or account access were identified.",
            "desc_ar": "تم العثور على كلمات مرتبطة بالتحقق أو بيانات الدخول أو الحسابات أو المعاملات.",
            "desc_en": "Terms related to verification, credentials, banking, or account access were identified."
        })

    if high_inbound_ratio:
        flags.append({
            "level": "warn",
            "title": "High inbound communication pattern",
            "title_ar": "نمط استقبال مرتفع للرسائل",
            "title_en": "High inbound communication pattern",
            "description": "The user receives significantly more messages than they send.",
            "desc": "The user receives significantly more messages than they send.",
            "desc_ar": "المستخدم يستقبل رسائل أكثر بكثير مما يرسل، وقد يشير ذلك إلى سلوك استهداف أو تلقي مكثف.",
            "desc_en": "The user receives significantly more messages than they send."
        })

    if has_external_urls and has_otp and has_sensitive_keywords:
        flags.append({
            "level": "danger",
            "title": "Combined phishing-related indicators observed",
            "title_ar": "تم رصد مؤشرات مجتمعة قد تدل على تصيد",
            "title_en": "Combined phishing-related indicators observed",
            "description": "The presence of links, verification codes, and sensitive keywords may indicate phishing or social engineering activity.",
            "desc": "The presence of links, verification codes, and sensitive keywords may indicate phishing or social engineering activity.",
            "desc_ar": "وجود روابط مع أكواد تحقق وكلمات حساسة قد يشير إلى محاولة تصيد أو هندسة اجتماعية.",
            "desc_en": "The presence of links, verification codes, and sensitive keywords may indicate phishing or social engineering activity."
        })

        if has_non_saudi:
            flags.append({
        "level": "warn",
        "title": "Non-Saudi number contacted",
        "title_ar": "تم التواصل مع رقم غير سعودي",
        "title_en": "Non-Saudi number contacted",
        "description": "A foreign phone number was identified.",
        "desc": "A foreign phone number was identified.",
        "desc_ar": "تم رصد رقم غير سعودي ضمن المحادثة.",
        "desc_en": "A foreign phone number was identified."
    })

    if not flags:
        flags.append({
            "level": "ok",
            "title": "No strong forensic indicators identified",
            "title_ar": "لم يتم العثور على مؤشرات جنائية قوية",
            "title_en": "No strong forensic indicators identified",
            "description": "The current message set does not contain strong suspicious indicators based on the available rules.",
            "desc": "The current message set does not contain strong suspicious indicators based on the available rules.",
            "desc_ar": "الرسائل الحالية لا تحتوي على مؤشرات مشبوهة قوية وفقًا لقواعد التحليل الحالية.",
            "desc_en": "The current message set does not contain strong suspicious indicators based on the available rules."
        })

    return flags


def detect_suspicious_flow(messages, urls, numbers, keywords):
    has_url = len(urls) > 0
    has_otp = any(n.get("type") == "otp" for n in numbers)

    keyword_set = {k["keyword"].lower() for k in keywords}
    has_verification_keywords = bool(keyword_set.intersection({w.lower() for w in VERIFICATION_TERMS}))
    has_financial_keywords = bool(keyword_set.intersection({w.lower() for w in FINANCIAL_TERMS}))

    if has_url and has_otp and has_verification_keywords:
        return {
            "level": "danger",
            "text_en": "Suspicious flow detected: link shared followed by verification-related content and code patterns.",
            "text_ar": "تم رصد تسلسل مشبوه: مشاركة رابط تبعتها محتويات مرتبطة بالتحقق ثم ظهور أكواد.",
        }

    if has_url and has_verification_keywords:
        return {
            "level": "warn",
            "text_en": "Potentially suspicious flow detected: external link with verification-related language.",
            "text_ar": "تم رصد تسلسل قد يكون مشبوهاً: رابط خارجي مع عبارات مرتبطة بالتحقق.",
        }

    if has_otp and has_verification_keywords:
        return {
            "level": "warn",
            "text_en": "Potentially suspicious flow detected: verification-related language with code patterns.",
            "text_ar": "تم رصد تسلسل قد يكون مشبوهاً: عبارات تحقق مع ظهور أكواد.",
        }

    if has_url and has_financial_keywords:
        return {
            "level": "warn",
            "text_en": "Potentially suspicious flow detected: external link with financial-related language.",
            "text_ar": "تم رصد تسلسل قد يكون مشبوهاً: رابط خارجي مع عبارات مالية أو بنكية.",
        }

    return None


def get_top_suspicious_message(messages):
    best_msg = None
    best_score = 0

    for msg in messages:
        text = (msg.get("text") or "").strip()
        if not text:
            continue

        text_lower = text.lower()
        score = 0

        has_url = bool(URL_REGEX.search(text))
        has_otp = bool(OTP_REGEX.search(text))
        has_verification = any(term.lower() in text_lower for term in VERIFICATION_TERMS)
        has_financial = any(term.lower() in text_lower for term in FINANCIAL_TERMS)
        has_urgent = any(term.lower() in text_lower for term in URGENT_TERMS)

        if has_url:
            score += 2
        if has_otp:
            score += 3
        if has_verification:
            score += 2
        if has_financial:
            score += 2
        if has_urgent:
            score += 1

        if score > best_score:
            best_score = score
            best_msg = msg

    if best_score < 3 or not best_msg:
        return None

    preview = best_msg["text"][:160].strip()

    return {
        "score": best_score,
        "message_id": best_msg.get("id"),
        "datetime": best_msg.get("datetime") or "-",
        "text_preview": preview,
        "text_preview_ar": preview,
        "text_preview_en": preview
    }


def build_recommendations(urls, numbers, keywords, messages, flow, top_suspicious_message):
    recs_ar = []
    recs_en = []

    has_url = len(urls) > 0
    has_otp = any(n.get("type") == "otp" for n in numbers)
    has_phone = any(n.get("type") == "phone" for n in numbers)

    keyword_set = {k["keyword"].lower() for k in keywords}
    has_verification_keywords = bool(keyword_set.intersection({w.lower() for w in VERIFICATION_TERMS}))
    has_financial_keywords = bool(keyword_set.intersection({w.lower() for w in FINANCIAL_TERMS}))

    if flow is not None:
        recs_ar.append("راجع تسلسل الرسائل زمنيًا للتأكد من سياق الرابط أو الكود قبل اعتبارها محاولة مشبوهة.")
        recs_en.append("Review the message sequence chronologically to verify the context of the link or code before treating it as suspicious.")

    if has_url:
        recs_ar.append("تحقق من الروابط الظاهرة في المحادثة قبل فتحها أو الاعتماد عليها.")
        recs_en.append("Validate any URLs appearing in the conversation before opening or relying on them.")

    if has_otp:
        recs_ar.append("لا تتم مشاركة أكواد التحقق المستخرجة من المحادثة ما لم يثبت أنها جزء من إجراء مشروع.")
        recs_en.append("Do not share verification codes extracted from the conversation unless they are confirmed to be part of a legitimate process.")

    if has_financial_keywords:
        recs_ar.append("راجع الرسائل ذات الطابع المالي أو البنكي يدويًا للتأكد من مشروعيتها.")
        recs_en.append("Manually review messages with financial or banking language to assess legitimacy.")

    if top_suspicious_message is not None:
        recs_ar.append("ابدأ المراجعة اليدوية بالرسالة الأعلى اشتباهاً ثم اربطها بباقي الرسائل المحيطة بها.")
        recs_en.append("Start manual review with the highest-scoring suspicious message and correlate it with surrounding messages.")

    if has_phone and (has_url or has_verification_keywords):
        recs_ar.append("راجع هوية المرسل وسياق التواصل معه قبل اتخاذ إجراء أو مشاركة بيانات إضافية.")
        recs_en.append("Review sender identity and communication context before taking action or sharing additional information.")

    if not recs_ar:
        recs_ar.append("لا توجد توصية تصعيدية فورية؛ يوصى بالاحتفاظ بالنتائج كمرجع تحليلي فقط.")
        recs_en.append("No immediate escalatory action is recommended; keep the results as an analytical reference only.")

    return {
        "items_ar": recs_ar,
        "items_en": recs_en
    }


def save_analysis_report(analysis_result, case_id, base_cases_dir="Cases"):
    case_dir = os.path.join(base_cases_dir, case_id)
    analysis_dir = os.path.join(case_dir, "Analysis")
    os.makedirs(analysis_dir, exist_ok=True)

    report_path = os.path.join(analysis_dir, "analysis_report.json")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)

    return report_path
