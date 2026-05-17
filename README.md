# Whisper-WA

Whisper-WA is a digital forensics platform designed for extracting, decrypting, and analyzing WhatsApp data from Android devices.

The system helps investigators perform WhatsApp forensic investigations through a simplified workflow and an investigator-focused interface.

---

## Purpose

The purpose of Whisper-WA is to simplify WhatsApp forensic investigations and help investigators analyze digital evidence in a more organized and efficient way.

---

## Features

* WhatsApp data extraction using ADB
* WhatsApp database decryption
* Chat and artifact analysis
* Suspicious links and keyword detection
* PDF and CSV forensic reports
* Arabic and English language support

---

## Tools & Technologies

* Python
* Flask
* SQLite
* HTML, CSS, JavaScript
* ADB
* wadecrypt

---

## Requirements

* Android device
* **Rooted Android device**
* Python 3.8+
* ADB installed
* wadecrypt tool

> Root access is required because the system needs access to the WhatsApp encryption key stored inside protected Android directories.

---

## Workflow

1. Connect Android device
2. Extract WhatsApp database and key
3. Decrypt the database
4. Analyze chats and artifacts
5. Generate forensic reports

---

## Project Poster

Project poster will be added here.

---

## Demo Video
[Watch Demo](https://drive.google.com/file/d/14Q1XjRKwIANJPaPd_XlTTlvyng1xaxCz/view?usp=sharing)

---

## System Interfaces

[View Interfaces PDF](Interfaces.pdf)

---

# How to Run the Project

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

using VS Code Live Server or any local web server.

---

## Important Notes

* The Android device must be rooted.
* Make sure `wadecrypt.exe` is located inside the `Backend` folder.
* ADB files are included in the project.
* If decryption does not work, verify that the WhatsApp key and `msgstore.db.crypt14` were extracted successfully from the device.
