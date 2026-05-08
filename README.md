# Whisper-WA

Whisper-WA is a digital forensics platform for extracting, decrypting, and analyzing WhatsApp data from Android devices.

The system helps investigators perform WhatsApp forensic analysis through a simplified workflow and investigator-focused interface.

---

# Features

- WhatsApp data extraction using ADB
- WhatsApp database decryption
- Chat and artifact analysis
- Suspicious links and keyword detection
- PDF and CSV forensic reports
- Arabic and English support

---

# Tools & Technologies

- Python
- Flask
- SQLite
- HTML, CSS, JavaScript
- ADB
- wadecrypt

---

# Requirements

- Android device
- Rooted Android device
- Python 3.8+
- ADB installed
- wadecrypt tool

> Root access is required because the system needs access to the WhatsApp encryption key stored inside protected Android directories.

---

# How to Run

```bash
git clone https://github.com/emtnansaadmhm-lang/whisper-wa2.git

cd whisper-wa2

pip install -r requirements.txt

cd Backend
python app.py
```

Then open:

```text
Frontend/index.html
```

using Live Server or any local web server.

---

# Workflow

1. Connect Android device
2. Extract WhatsApp database and key
3. Decrypt the database
4. Analyze chats and artifacts
5. Generate forensic reports

---

# Project Poster

Project poster will be added here.

---

# Demo Video

Project demo video will be added here.

---

# System Interfaces

System interface screenshots will be added here.

---

# Purpose

The purpose of Whisper-WA is to simplify WhatsApp forensic investigations and help investigators analyze digital evidence in a more organized and efficient way.
