import os
import re
import json
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse


URL_REGEX = re.compile(r'(?:https?://|www\.)[^\s<>()]+', re.IGNORECASE)
PHONE_REGEX = re.compile(r'(?<!\d)(?:\+|00)?\d[\d\s\-()]{6,}\d(?!\d)')
OTP_REGEX = re.compile(r'(?<!\d)\d{4,8}(?!\d)')
FILE_REGEX = re.compile(r'\b\S+\.(pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|7z|apk|exe|msi|bat|cmd|js|vbs|scr|csv|txt)\b', re.IGNORECASE)
DANGEROUS_FILE_REGEX = re.compile(r'\b\S+\.(apk|exe|msi|bat|cmd|js|vbs|scr)\b', re.IGNORECASE)


KEYWORDS = [
    # Access / Identity
    "otp", "one time password", "verification", "verify", "verification code", "security code",
    "code", "pin", "passcode", "password", "reset password", "username", "login", "sign in",
    "signin", "account", "credentials", "2fa", "mfa", "auth", "confirm", "security", "reset",

    # Financial / Banking
    "bank", "card", "credit card", "debit card", "cvv", "iban", "account number", "wallet",
    "payment", "pay now", "transfer", "wire transfer", "invoice", "refund", "transaction",
    "balance", "deposit", "withdraw", "cash", "fee", "tax",

    # Pressure / Social Engineering
    "urgent", "important", "immediately", "asap", "final notice", "last chance",
    "action required", "limited time", "blocked", "suspended", "locked", "restricted",
    "disabled", "verify now", "confirm now", "update required", "now", "quick",

    # Click / Phishing behavior
    "click", "click here", "open link", "tap", "download", "install", "update",
    "scan", "check link", "complete your information", "confirm your information",
    "do not share", "dont share", "don't share", "share this code", "send the code",

    # Prize / Scam lure
    "winner", "prize", "gift", "reward", "bonus", "claim", "congratulations",
    "free", "offer", "lottery", "promotion", "subscription", "job offer",
    "investment", "profit", "loan", "delivery", "shipment", "tracking", "customs", "unpaid",

    # Malware / Suspicious file behavior
    "apk", "exe", "install app", "unknown app", "security update", "system update",
    "remote access", "tracking app", "spy", "malware"
]

AR_KEYWORDS = [
    # Access / Identity
    "كود", "رمز", "رمز التحقق", "كود التحقق", "رقم سري", "الرقم السري",
    "كلمة المرور", "كلمة السر", "تسجيل دخول", "تحقق", "تأكيد", "تفعيل",
    "توثيق", "بيانات الدخول", "بياناتك", "حسابك", "أرسل الرمز", "ارسل الرمز",
    "لا تشارك", "لا ترسل الرمز", "ارسل الكود", "أرسل الكود",

    # Financial / Banking
    "بنك", "البنك", "حساب", "حساب بنكي", "بطاقة", "بطاقة ائتمانية",
    "مدى", "فيزا", "ايبان", "آيبان", "تحويل", "حوالة", "دفع", "سداد",
    "فاتورة", "رسوم", "ضريبة", "مبلغ", "رصيد", "سحب", "إيداع", "ايداع",
    "محفظة", "استرداد",

    # Pressure / Threat
    "عاجل", "ضروري", "مهم", "تنبيه", "تحذير", "آخر فرصة", "اخر فرصة",
    "سيتم إغلاق", "سيتم اغلاق", "إيقاف الحساب", "ايقاف الحساب", "تم إيقاف",
    "تم ايقاف", "حسابك موقوف", "حسابك معلق", "محظور", "معلق", "مقيد",
    "حسابك معرض", "تحديث مطلوب", "الآن", "الان", "فوراً", "فورا",

    # Click / Phishing behavior
    "اضغط", "اضغط هنا", "افتح الرابط", "الرابط", "تحميل", "حمل",
    "تثبيت", "حدث التطبيق", "تحديث", "فحص", "افحص", "أكمل بياناتك",
    "اكمل بياناتك", "أكد بياناتك", "اكد بياناتك", "تأكيد البيانات",
    "ادخل بياناتك", "سجل دخولك",

    # Prize / Scam lure
    "فزت", "ربحت", "جائزة", "هدية", "مجانا", "مجاناً", "اربح",
    "مبروك", "مكافأة", "مكافاه", "استلم", "استلام", "عرض", "ترقية",
    "شحنة", "توصيل", "تتبع الشحنة", "الجمارك", "رسالة من البنك",
    "وظيفة", "استثمار", "ربح", "قرض", "دعم"
]

VERIFICATION_TERMS = {
    "otp", "one time password", "code", "verification", "verify", "verification code",
    "security code", "login", "account", "password", "pin", "confirm", "security",
    "reset", "2fa", "mfa",
    "كود", "رمز", "رمز التحقق", "كود التحقق", "تحقق", "تأكيد", "حساب",
    "رقم سري", "كلمة المرور", "كلمة السر", "استرجاع", "تفعيل", "توثيق"
}

FINANCIAL_TERMS = {
    "bank", "transfer", "payment", "wallet", "refund", "iban", "card",
    "credit card", "debit card", "cvv", "account number", "transaction",
    "بنك", "البنك", "تحويل", "دفع", "ايبان", "آيبان", "بطاقة", "حساب بنكي",
    "حوالة", "سداد", "فاتورة", "محفظة", "استرداد"
}

URGENT_TERMS = {
    "urgent", "immediately", "now", "asap", "quick", "final notice", "last chance",
    "action required", "limited time", "blocked", "suspended", "locked", "restricted",
    "disabled", "verify now", "confirm now",
    "عاجل", "الآن", "الان", "فوراً", "فورا", "ضروري", "مهم", "آخر فرصة",
    "اخر فرصة", "حسابك موقوف", "حسابك معلق", "سيتم إغلاق", "سيتم اغلاق"
}

SCAM_LURE_TERMS = {
    "winner", "prize", "gift", "reward", "bonus", "claim", "congratulations",
    "free", "offer", "lottery", "promotion", "job offer", "investment", "profit",
    "loan", "delivery", "shipment", "tracking", "customs", "unpaid",
    "فزت", "ربحت", "جائزة", "هدية", "مكافأة", "مكافاه", "مبروك", "استلم",
    "استلام", "مجانا", "مجاناً", "عرض", "وظيفة", "استثمار", "ربح", "قرض",
    "شحنة", "توصيل", "تتبع الشحنة", "الجمارك"
}

INSTALL_TERMS = {
    "download", "install", "update", "security update", "system update", "open file",
    "تحميل", "حمل", "تثبيت", "ثبت", "تحديث", "حدث التطبيق", "افتح الملف"
}

FAMOUS_DOMAINS = [
    # Global
    "apple.com", "appleid.apple.com", "icloud.com", "paypal.com", "google.com",
    "gmail.com", "accounts.google.com", "microsoft.com", "office.com", "outlook.com",
    "live.com", "facebook.com", "instagram.com", "whatsapp.com", "amazon.com",
    "netflix.com", "x.com", "twitter.com", "linkedin.com", "snapchat.com", "tiktok.com",
    "youtube.com",

    # Saudi telecom / gov / identity
    "stc.com.sa", "my.stc.com.sa", "mobily.com.sa", "zain.com", "absher.sa",
    "iam.gov.sa", "nafath.sa", "my.gov.sa", "moi.gov.sa", "moe.gov.sa",
    "moh.gov.sa", "zatca.gov.sa", "najiz.sa", "etimad.sa", "gosi.gov.sa",
    "balady.gov.sa", "tawakkalna.gov.sa", "sdaia.gov.sa", "saudibusiness.gov.sa",

    # Saudi banks / finance
    "alrajhibank.com.sa", "alrajhi.com", "riyadbank.com", "bankalbilad.com",
    "alinma.com", "snb.com.sa", "alahli.com", "sab.com", "anb.com.sa",
    "bankaljazira.com", "saib.com.sa", "fransibank.com.sa", "mada.com.sa",
    "stcpay.com.sa", "urpay.com.sa", "tamara.co", "tabby.ai",

    # Delivery / commerce
    "splonline.com.sa", "saudipost.sa", "aramex.com", "dhl.com", "fedex.com",
    "ups.com", "smsaexpress.com", "noon.com", "jarir.com", "extra.com",
    "hungerstation.com", "jahez.net", "mrsool.co",

    # Large local orgs
    "aramco.com", "sabic.com", "neom.com", "stc.com", "redsea.com"
]


def analyze_whatsapp_data(messages, case_id):
    try:
        if not messages:
            return {"ok": False, "error": "No messages to analyze"}

        normalized = normalize_messages(messages)

        urls = extract_urls(normalized)
        numbers = extract_numbers(normalized)
        keywords = extract_keywords(normalized)
        summary = build_summary(normalized, urls, numbers, keywords)
        activity = build_activity(normalized)
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
        msg_type = str(msg.get("type", "")).strip().lower()

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

            # الرقم الصحيح القادم من messages_api
            "user": msg.get("user", ""),

            # fallback فقط
            "contact_name": msg.get("contact_name", ""),
            "remote_jid": msg.get("remote_jid", ""),
            "media_name": msg.get("media_name", ""),
            "media_url": msg.get("media_url", ""),
            "media_type": msg.get("media_type", ""),
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


def build_summary(messages, urls=None, numbers=None, keywords=None):
    urls = urls if urls is not None else extract_urls(messages)
    numbers = numbers if numbers is not None else extract_numbers(messages)
    keywords = keywords if keywords is not None else extract_keywords(messages)

    total = len(messages)
    sent = sum(1 for m in messages if m["from_me"])
    received = total - sent

    datetimes = [m["dt_obj"] for m in messages if m["dt_obj"] is not None]
    datetimes.sort()

    first_contact = datetimes[0].strftime("%Y-%m-%d %H:%M:%S") if datetimes else "-"
    last_contact = datetimes[-1].strftime("%Y-%m-%d %H:%M:%S") if datetimes else "-"

    non_saudi_count = sum(
        1 for n in numbers
        if n.get("is_non_saudi") and n.get("type") == "foreign_contact"
    )

    spoofing_count = sum(1 for u in urls if u.get("is_spoofing"))

    return {
        "total_messages": total,
        "sent": sent,
        "received": received,
        "first_contact": first_contact,
        "last_contact": last_contact,
        "urls_count": len(urls),
        "spoofing_urls_count": spoofing_count,
        "numbers_count": len(numbers),
        "non_saudi_numbers_count": non_saudi_count,
        "emails_count": 0,
        "keyword_hits_total": sum(k.get("hits", 0) for k in keywords)
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
    ])

    return activity_items


def extract_urls(messages):
    counter = Counter()

    for msg in messages:
        text = msg.get("text", "")
        found = URL_REGEX.findall(text)
        for raw_url in found:
            cleaned = str(raw_url).strip().rstrip("),.;!?")
            if cleaned:
                counter[cleaned] += 1

    results = []
    for url, count in counter.most_common(30):
        spoof = get_spoofing_match(url)
        item = {
            "url": url,
            "count": count,
            "domain": extract_domain(url),
            "is_spoofing": bool(spoof),
        }
        if spoof:
            item.update({
                "spoofing_suspicious_domain": spoof.get("suspicious"),
                "spoofing_resembles": spoof.get("resembles"),
                "spoofing_suggestions": spoof.get("suggestions", []),
                "risk": "high",
                "note_ar": f"رابط مزيف محتمل يشبه {spoof.get('resembles')}",
                "note_en": f"Possible spoofed URL resembling {spoof.get('resembles')}",
            })
        results.append(item)

    return results


def extract_numbers(messages):
    number_map = {}

    for msg in messages:
        text = msg.get("text", "")

        phones = PHONE_REGEX.findall(text)
        otps = OTP_REGEX.findall(text)

        for p in phones:
            value = clean_number(p)
            digits = normalize_phone_digits(value)

            # منع تصنيف OTP أو أرقام قصيرة كرقم تواصل
            if not is_valid_phone_number(value):
                continue

            # لا نعتبر الرقم أجنبي إلا إذا كان بصيغة دولية واضحة + أو 00
            is_international = str(value).startswith("+") or str(value).startswith("00")
            is_non_saudi = is_international and not is_saudi_number(value)

            item_type = "foreign_contact" if is_non_saudi else "phone"

            if value not in number_map:
                number_map[value] = {
                    "value": value,
                    "type": item_type,
                    "is_non_saudi": is_non_saudi,
                    "context": "Foreign phone number found in message" if is_non_saudi else "Phone number mentioned in message",
                    "context_ar": "رقم دولي غير سعودي مذكور داخل رسالة" if is_non_saudi else "رقم هاتف مذكور داخل رسالة",
                    "context_en": "Foreign phone number found in message" if is_non_saudi else "Phone number mentioned in message",
                    "count": 0
                }
            number_map[value]["count"] += 1

        for o in otps:
            if len(o) < 4 or len(o) > 8:
                continue

            # إذا الرقم انحسب كجوال لا نعيده OTP
            if o in number_map and number_map[o].get("type") in ("phone", "foreign_contact"):
                continue

            if o not in number_map:
                number_map[o] = {
                    "value": o,
                    "type": "otp",
                    "is_non_saudi": False,
                    "context": "Possible OTP or verification code",
                    "context_ar": "كود تحقق أو OTP محتمل",
                    "context_en": "Possible OTP or verification code",
                    "count": 0
                }
            number_map[o]["count"] += 1

    items = list(number_map.values())
    items.sort(key=lambda x: x["count"], reverse=True)
    return items[:30]


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
    raw = clean_number(value)
    digits = normalize_phone_digits(raw)

    if not digits.isdigit():
        return False

    if not (8 <= len(digits) <= 15):
        return False

    # أرقام OTP الشائعة 4-8 لا تصير phone إلا إذا كانت بصيغة دولية واضحة
    if len(digits) <= 8 and not (raw.startswith("+") or raw.startswith("00")):
        return False

    return True


def extract_keywords(messages):
    hits = defaultdict(lambda: {"hits": 0, "examples": []})
    all_keywords = KEYWORDS + AR_KEYWORDS

    for msg in messages:
        text = msg.get("text", "")
        lower_text = text.lower()

        for kw in all_keywords:
            kw_lower = kw.lower()
            if kw_lower in lower_text:
                hits[kw]["hits"] += 1
                if len(hits[kw]["examples"]) < 3:
                    hits[kw]["examples"].append(text[:160])

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
    return results[:30]


def extract_domain(url):
    try:
        clean = str(url or "").strip().rstrip("),.;!?")
        if not clean:
            return ""
        if not clean.startswith(("http://", "https://")):
            clean = "https://" + clean
        host = urlparse(clean).hostname or ""
        return host.lower().replace("www.", "")
    except Exception:
        return ""


def normalize_domain_name(value):
    return str(value or "").lower() \
        .replace("0", "o").replace("1", "l").replace("3", "e").replace("4", "a") \
        .replace("5", "s").replace("7", "t").replace("8", "b") \
        .replace("|", "l").replace("!", "l").replace("$", "s") \
        .replace("rn", "m") \
        .replace("-", "").replace("_", "").replace(".", "")


def levenshtein(a, b):
    a = str(a or "")
    b = str(b or "")
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]

    for i in range(len(a) + 1):
        dp[i][0] = i
    for j in range(len(b) + 1):
        dp[0][j] = j

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost
            )

    return dp[-1][-1]


def get_main_domain_name(domain):
    parts = str(domain or "").split(".")
    if len(parts) >= 3 and parts[-2] in {"com", "net", "org", "gov", "edu"}:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


def get_spoofing_match(url_or_text):
    urls = URL_REGEX.findall(str(url_or_text or ""))
    if not urls and "." in str(url_or_text or ""):
        urls = [str(url_or_text)]

    for raw in urls:
        domain = extract_domain(raw)
        if not domain:
            continue

        if domain in FAMOUS_DOMAINS:
            continue

        main_norm = normalize_domain_name(get_main_domain_name(domain))
        if not main_norm or len(main_norm) < 3:
            continue

        for official in FAMOUS_DOMAINS:
            official_main = get_main_domain_name(official)
            official_norm = normalize_domain_name(official_main)

            if not official_norm or len(official_norm) < 3:
                continue

            if domain == official or main_norm == official_norm:
                continue

            distance = levenshtein(main_norm, official_norm)
            close_length = abs(len(main_norm) - len(official_norm)) <= 3
            same_start = main_norm[0] == official_norm[0]
            contains_brand = (
                official_norm in main_norm and main_norm != official_norm
            ) or (
                main_norm in official_norm and main_norm != official_norm and len(main_norm) >= 4
            )
            typo_squat = close_length and same_start and 0 < distance <= 2
            short_brand_typo = len(official_norm) <= 5 and close_length and 0 < distance <= 2

            if contains_brand or typo_squat or short_brand_typo:
                suggestions = [
                    d for d in FAMOUS_DOMAINS
                    if official_main in d or get_main_domain_name(d) in official_main
                ][:8]
                return {
                    "suspicious": domain,
                    "resembles": official,
                    "suggestions": suggestions if suggestions else [official]
                }

    return None


def message_has_any_term(text, terms):
    lower = str(text or "").lower()
    return any(str(term).lower() in lower for term in terms)


def message_score(msg):
    text = (msg.get("text") or "").strip()
    if not text:
        return 0, []

    reasons = []
    score = 0

    spoof = get_spoofing_match(text)
    has_url = bool(URL_REGEX.search(text))
    has_otp = bool(OTP_REGEX.search(text))
    has_verification = message_has_any_term(text, VERIFICATION_TERMS)
    has_financial = message_has_any_term(text, FINANCIAL_TERMS)
    has_urgent = message_has_any_term(text, URGENT_TERMS)
    has_scam_lure = message_has_any_term(text, SCAM_LURE_TERMS)
    has_dangerous_file = bool(DANGEROUS_FILE_REGEX.search(text))
    has_file = bool(FILE_REGEX.search(text))
    has_install = message_has_any_term(text, INSTALL_TERMS)

    if spoof:
        score += 6
        reasons.append({
            "type": "spoofing",
            "ar": f"رابط مزيف محتمل يشبه {spoof.get('resembles')}",
            "en": f"Possible spoofed URL resembling {spoof.get('resembles')}"
        })

    if has_dangerous_file:
        score += 5
        reasons.append({
            "type": "dangerous_file",
            "ar": "ملف تنفيذي أو امتداد عالي الخطورة",
            "en": "Executable or high-risk file extension"
        })

    if has_scam_lure:
        score += 3
        reasons.append({
            "type": "scam_lure",
            "ar": "عبارات إغراء احتيالي مثل جائزة أو هدية",
            "en": "Scam lure terms such as prize, gift, or reward"
        })

    if has_otp:
        score += 3
        reasons.append({
            "type": "otp",
            "ar": "نمط رقمي يشبه كود تحقق",
            "en": "Numeric pattern resembling an OTP"
        })

    if has_financial:
        score += 2
        reasons.append({
            "type": "financial",
            "ar": "عبارات مالية أو بنكية",
            "en": "Financial or banking language"
        })

    if has_verification:
        score += 2
        reasons.append({
            "type": "verification",
            "ar": "عبارات تحقق أو بيانات دخول",
            "en": "Verification or credential-related language"
        })

    if has_urgent:
        score += 2
        reasons.append({
            "type": "urgency",
            "ar": "ضغط أو استعجال اجتماعي",
            "en": "Urgency or social pressure language"
        })

    # الرابط العادي وحده ما يكفي، نعطيه نقطة قليلة فقط
    if has_url:
        score += 1
        reasons.append({
            "type": "url",
            "ar": "رابط خارجي",
            "en": "External URL"
        })

    if has_file and has_install:
        score += 3
        reasons.append({
            "type": "file_install",
            "ar": "ملف مع تعليمات تحميل أو تثبيت",
            "en": "File with download or install instructions"
        })

    return score, reasons


def build_flags(urls, numbers, keywords, messages):
    flags = []

    shorteners = ("bit.ly", "tinyurl", "t.co", "goo.gl", "is.gd", "cutt.ly", "shorturl.at")
    has_shortened_url = any(
        any(short in item.get("url", "").lower() for short in shorteners)
        for item in urls
    )

    spoofed_urls = [u for u in urls if u.get("is_spoofing")]
    has_spoofing = len(spoofed_urls) > 0
    has_external_urls = len(urls) > 0
    has_otp = any(item.get("type") == "otp" for item in numbers)
    has_non_saudi = any(
        item.get("is_non_saudi") and item.get("type") == "foreign_contact"
        for item in numbers
    )

    keyword_set = {k["keyword"].lower() for k in keywords}
    has_sensitive_keywords = bool(
        keyword_set.intersection({w.lower() for w in VERIFICATION_TERMS.union(FINANCIAL_TERMS)})
    )
    has_scam_keywords = bool(keyword_set.intersection({w.lower() for w in SCAM_LURE_TERMS}))
    has_urgent_keywords = bool(keyword_set.intersection({w.lower() for w in URGENT_TERMS}))

    dangerous_file_messages = [
        m for m in messages
        if DANGEROUS_FILE_REGEX.search(m.get("text", ""))
    ]

    if has_spoofing:
        first = spoofed_urls[0]
        flags.append({
            "level": "danger",
            "title": "Spoofed URL detected",
            "title_ar": "تم رصد رابط مزيف محتمل",
            "title_en": "Spoofed URL detected",
            "description": f"A URL resembling a trusted domain was detected: {first.get('domain')} resembles {first.get('spoofing_resembles')}.",
            "desc": f"A URL resembling a trusted domain was detected: {first.get('domain')} resembles {first.get('spoofing_resembles')}.",
            "desc_ar": f"تم رصد رابط قد ينتحل جهة موثوقة: {first.get('domain')} يشبه {first.get('spoofing_resembles')}.",
            "desc_en": f"A URL resembling a trusted domain was detected: {first.get('domain')} resembles {first.get('spoofing_resembles')}."
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

    if has_external_urls and (has_sensitive_keywords or has_scam_keywords or has_urgent_keywords):
        flags.append({
            "level": "warn",
            "title": "URL combined with social-engineering language",
            "title_ar": "رابط مع عبارات هندسة اجتماعية",
            "title_en": "URL combined with social-engineering language",
            "description": "A URL appeared with verification, urgency, financial, or reward-related wording.",
            "desc": "A URL appeared with verification, urgency, financial, or reward-related wording.",
            "desc_ar": "ظهر رابط مع عبارات تحقق أو استعجال أو كلمات مالية أو إغراءات مثل الهدايا والجوائز.",
            "desc_en": "A URL appeared with verification, urgency, financial, or reward-related wording."
        })

    if has_otp and (has_sensitive_keywords or has_external_urls):
        flags.append({
            "level": "danger",
            "title": "Possible OTP involved in suspicious context",
            "title_ar": "كود تحقق محتمل ضمن سياق مشبوه",
            "title_en": "Possible OTP involved in suspicious context",
            "description": "Numeric patterns resembling OTP codes were found with URLs or verification-related terms.",
            "desc": "Numeric patterns resembling OTP codes were found with URLs or verification-related terms.",
            "desc_ar": "تم العثور على أرقام تشبه أكواد التحقق مع روابط أو كلمات مرتبطة بالتحقق.",
            "desc_en": "Numeric patterns resembling OTP codes were found with URLs or verification-related terms."
        })

    if has_scam_keywords:
        flags.append({
            "level": "warn",
            "title": "Scam lure keywords detected",
            "title_ar": "تم رصد عبارات إغراء احتيالي",
            "title_en": "Scam lure keywords detected",
            "description": "Terms such as prize, gift, winner, reward, or similar lure language were detected.",
            "desc": "Terms such as prize, gift, winner, reward, or similar lure language were detected.",
            "desc_ar": "تم رصد عبارات مثل فزت أو هدية أو جائزة أو مكافأة وقد تستخدم في الاحتيال.",
            "desc_en": "Terms such as prize, gift, winner, reward, or similar lure language were detected."
        })

    if has_sensitive_keywords:
        flags.append({
            "level": "warn",
            "title": "Sensitive verification or banking keywords detected",
            "title_ar": "تم رصد كلمات حساسة مرتبطة بالتحقق أو المعاملات",
            "title_en": "Sensitive verification or banking keywords detected",
            "description": "Terms related to verification, credentials, banking, or account access were identified.",
            "desc": "Terms related to verification, credentials, banking, or account access were identified.",
            "desc_ar": "تم العثور على كلمات مرتبطة بالتحقق أو بيانات الدخول أو الحسابات أو المعاملات.",
            "desc_en": "Terms related to verification, credentials, banking, or account access were identified."
        })

    if dangerous_file_messages:
        flags.append({
            "level": "danger",
            "title": "Potentially dangerous file reference detected",
            "title_ar": "تم رصد ملف أو امتداد عالي الخطورة",
            "title_en": "Potentially dangerous file reference detected",
            "description": "Executable or script-like file extensions were found and should be reviewed manually.",
            "desc": "Executable or script-like file extensions were found and should be reviewed manually.",
            "desc_ar": "تم رصد امتدادات تنفيذية أو سكربتات مثل APK/EXE/JS/VBS ويجب مراجعتها يدويًا.",
            "desc_en": "Executable or script-like file extensions were found and should be reviewed manually."
        })

    if has_non_saudi:
        flags.append({
            "level": "warn",
            "title": "Foreign phone number found",
            "title_ar": "تم رصد رقم دولي غير سعودي",
            "title_en": "Foreign phone number found",
            "description": "An international non-Saudi phone number was found in the message content.",
            "desc": "An international non-Saudi phone number was found in the message content.",
            "desc_ar": "تم رصد رقم دولي غير سعودي داخل محتوى الرسائل، وليس مجرد كود تحقق.",
            "desc_en": "An international non-Saudi phone number was found in the message content."
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
    # الفلو ما يطلع إلا إذا فيه سيناريو جنائي واضح، مو مجرد رابط عادي
    keyword_set = {k["keyword"].lower() for k in keywords}

    has_spoofing = any(u.get("is_spoofing") for u in urls)
    has_url = len(urls) > 0
    has_otp = any(n.get("type") == "otp" for n in numbers)
    has_verification_keywords = bool(keyword_set.intersection({w.lower() for w in VERIFICATION_TERMS}))
    has_financial_keywords = bool(keyword_set.intersection({w.lower() for w in FINANCIAL_TERMS}))
    has_scam_keywords = bool(keyword_set.intersection({w.lower() for w in SCAM_LURE_TERMS}))
    has_urgent_keywords = bool(keyword_set.intersection({w.lower() for w in URGENT_TERMS}))

    dangerous_file = any(DANGEROUS_FILE_REGEX.search(m.get("text", "")) for m in messages)
    install_language = any(message_has_any_term(m.get("text", ""), INSTALL_TERMS) for m in messages)

    if has_spoofing and (has_verification_keywords or has_financial_keywords or has_otp):
        return {
            "level": "danger",
            "scenario": "spoofing_with_sensitive_context",
            "text_en": "High-risk flow: spoofed URL appears with verification, financial, or OTP-related context.",
            "text_ar": "تسلسل عالي الخطورة: رابط مزيف محتمل ظهر مع سياق تحقق أو مالي أو كود OTP.",
        }

    if has_spoofing:
        return {
            "level": "danger",
            "scenario": "spoofed_url",
            "text_en": "Suspicious flow: spoofed domain resembling a trusted service was detected.",
            "text_ar": "تسلسل مشبوه: تم رصد رابط مزيف محتمل يشبه جهة موثوقة.",
        }

    if has_url and has_otp and has_verification_keywords:
        return {
            "level": "danger",
            "scenario": "link_otp_verification",
            "text_en": "Suspicious flow: URL combined with verification language and OTP-like code patterns.",
            "text_ar": "تسلسل مشبوه: رابط مع عبارات تحقق وظهور أرقام تشبه أكواد OTP.",
        }

    if has_url and has_scam_keywords:
        return {
            "level": "warn",
            "scenario": "prize_or_gift_link",
            "text_en": "Potential scam flow: reward, prize, or gift wording appeared with a URL.",
            "text_ar": "تسلسل احتيالي محتمل: عبارات فوز أو هدية أو جائزة ظهرت مع رابط.",
        }

    if has_url and has_financial_keywords:
        return {
            "level": "warn",
            "scenario": "financial_link",
            "text_en": "Potential phishing flow: financial or banking wording appeared with a URL.",
            "text_ar": "تسلسل تصيد محتمل: عبارات مالية أو بنكية ظهرت مع رابط.",
        }

    if has_url and has_urgent_keywords:
        return {
            "level": "warn",
            "scenario": "urgency_link",
            "text_en": "Potential social-engineering flow: urgency or pressure language appeared with a URL.",
            "text_ar": "تسلسل هندسة اجتماعية محتمل: عبارات استعجال أو ضغط ظهرت مع رابط.",
        }

    if dangerous_file and install_language:
        return {
            "level": "danger",
            "scenario": "dangerous_file_install",
            "text_en": "High-risk flow: executable or script-like file reference appeared with install/download wording.",
            "text_ar": "تسلسل عالي الخطورة: ملف تنفيذي أو سكربت ظهر مع عبارات تحميل أو تثبيت.",
        }

    return None


def get_top_suspicious_message(messages):
    best_msg = None
    best_score = 0
    best_reasons = []

    for msg in messages:
        score, reasons = message_score(msg)

        # الرابط العادي بدون سياق لا يعتبر Top Message
        if score > best_score:
            best_score = score
            best_msg = msg
            best_reasons = reasons

    if best_score < 5 or not best_msg:
        return None

    preview = best_msg["text"][:200].strip()

    return {
        "score": best_score,
        "message_id": best_msg.get("id"),
        "datetime": best_msg.get("datetime") or "-",
        "text_preview": preview,
        "text_preview_ar": preview,
        "text_preview_en": preview,
        "reasons": best_reasons,
        "reasons_ar": [r.get("ar") for r in best_reasons],
        "reasons_en": [r.get("en") for r in best_reasons],
    }


def build_recommendations(urls, numbers, keywords, messages, flow, top_suspicious_message):
    recs_ar = []
    recs_en = []

    spoofed_urls = [u for u in urls if u.get("is_spoofing")]
    has_url = len(urls) > 0
    has_spoofing = len(spoofed_urls) > 0
    has_otp = any(n.get("type") == "otp" for n in numbers)
    has_foreign = any(n.get("type") == "foreign_contact" and n.get("is_non_saudi") for n in numbers)

    keyword_set = {k["keyword"].lower() for k in keywords}
    has_verification_keywords = bool(keyword_set.intersection({w.lower() for w in VERIFICATION_TERMS}))
    has_financial_keywords = bool(keyword_set.intersection({w.lower() for w in FINANCIAL_TERMS}))
    has_scam_keywords = bool(keyword_set.intersection({w.lower() for w in SCAM_LURE_TERMS}))

    if has_spoofing:
        recs_ar.append("راجع الرابط المزيف المحتمل وقارنه بالنطاق الرسمي قبل اعتماده كدليل.")
        recs_en.append("Review the suspected spoofed URL and compare it with the official domain before relying on it as evidence.")

    if flow is not None:
        recs_ar.append("راجع تسلسل الرسائل زمنيًا واربط الرابط أو الكود بالرسائل السابقة واللاحقة.")
        recs_en.append("Review the message sequence chronologically and correlate the URL or code with surrounding messages.")

    if has_url:
        recs_ar.append("تحقق من جميع الروابط المستخرجة ولا تفتحها من بيئة العمل الأساسية.")
        recs_en.append("Validate extracted URLs and avoid opening them from the primary workstation.")

    if has_otp and has_verification_keywords:
        recs_ar.append("تعامل مع أكواد التحقق كبيانات حساسة وراجع هل طُلب من المستخدم مشاركتها.")
        recs_en.append("Treat OTP-like codes as sensitive and review whether the user was asked to share them.")

    if has_financial_keywords:
        recs_ar.append("راجع الرسائل ذات الطابع المالي أو البنكي يدويًا للتأكد من مشروعيتها.")
        recs_en.append("Manually review messages with financial or banking language to assess legitimacy.")

    if has_scam_keywords:
        recs_ar.append("افحص رسائل الجوائز أو الهدايا لأنها شائعة في الاحتيال والهندسة الاجتماعية.")
        recs_en.append("Inspect prize, gift, or reward messages because they are common in scam and social-engineering attempts.")

    if has_foreign:
        recs_ar.append("راجع الرقم الدولي غير السعودي ضمن سياق المحادثة للتأكد هل هو جهة تواصل حقيقية أو مجرد رقم مذكور.")
        recs_en.append("Review the international non-Saudi number in context to determine whether it is an actual contact or only mentioned text.")

    if top_suspicious_message is not None:
        recs_ar.append("ابدأ المراجعة اليدوية بالرسالة الأعلى اشتباهًا ثم اربطها بباقي المحادثة.")
        recs_en.append("Start manual review with the highest-scoring suspicious message and correlate it with the rest of the conversation.")

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
