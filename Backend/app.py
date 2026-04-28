from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import os

from connected import bp_connected
from messages_api import messages_api
from auth_routes import bp_auth
from export import bp_export
from reports import bp_reports
from analysis_api import bp_analysis
from cases_api import bp_cases

from models import db
from database import init_database

app = Flask(__name__)
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///whisper_wa.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
init_database(app)

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "service": "Whisper-WA Backend",
        "timestamp": datetime.now().isoformat()
    })

# =========================
# Serve WhatsApp Media Files
# =========================
@app.route("/api/media/<case_id>/<path:filename>", methods=["GET"])
def serve_case_media(case_id, filename):
    media_dir = os.path.join("Cases", case_id, "Evidence", "Media", "Media")
    return send_from_directory(media_dir, filename)

app.register_blueprint(bp_connected)
app.register_blueprint(messages_api)
app.register_blueprint(bp_auth)
app.register_blueprint(bp_export)
app.register_blueprint(bp_reports)
app.register_blueprint(bp_analysis)
app.register_blueprint(bp_cases)

if __name__ == "__main__":
    print("Starting Whisper-WA backend...")
    app.run(debug=True, host="0.0.0.0", port=5000)