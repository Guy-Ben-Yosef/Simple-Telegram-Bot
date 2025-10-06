import os
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Set TELEGRAM_TOKEN env var")

TG_API = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}"

@app.route("/", methods=["GET"])
def index():
    return "Telegram bot service - OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    chat_id = data["message"]["chat"]["id"]
    text = data["message"]["text"]
    requests.post(f"{TG_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": f"1. Echo: {text}\n2. Echo: {text*2}"
    }, timeout=5)
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
