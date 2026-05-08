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
