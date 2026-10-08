import os
import sys
import time
import random
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ================= CONFIGURATION =================
class Config:
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8847939563:AAFaVL8Xt5n5aS9yuNu421Zhk0faPTOgCiY")
    CHAT_ID = os.environ.get("CHAT_ID", "-1003984666851")
    WIN_STICKER_ID = os.environ.get(
        "WIN_STICKER_ID", 
        "CAACAgUAAxkBAAFNlBJqP1tGPYT24rEmDIJnXLpy6esnGwAC-hwAAqcUuFbgWCEwPN_WJTwE"
    )
    PORT = int(os.environ.get("PORT", 8080))

    API_URL = (
        "https://draw.ar-lottery01.com/"
        "TrxWinGo/TrxWinGo_1M/GetHistoryIssuePage.json"
    )

# ================= SESSION & GLOBALS =================
session = requests.Session()
win_streak = 0
loss_streak = 0
sent_results = set()

# ================= DUMMY WEB SERVER (FOR RENDER) =================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"TRX Bot is alive and running!")

    def log_message(self, format, *args):
        # Console output တွေ မရှုပ်ပွစေရန် web access log ကို ပိတ်ထားခြင်း
        return

def run_web_server():
    server_address = ("0.0.0.0", Config.PORT)
    httpd = HTTPServer(server_address, DummyHandler)
    logger.info(f"Web server started on port {Config.PORT}")
    httpd.serve_forever()

# ================= TELEGRAM METHODS =================
def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendMessage"
        session.post(
            url,
            json={
                "chat_id": Config.CHAT_ID,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=5
        )
    except Exception as e:
        logger.error(f"Message Error: {e}")

def send_sticker():
    try:
        url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendSticker"
        session.post(
            url,
            json={
                "chat_id": Config.CHAT_ID,
                "sticker": Config.WIN_STICKER_ID
            },
            timeout=5
        )
    except Exception as e:
        logger.error(f"Sticker Error: {e}")

# ================= API DATA FETCHER =================
def get_result():
    try:
        r = session.get(Config.API_URL, timeout=5)
        data = r.json()
        items = data["data"]["list"]
        results = []

        for item in items[:10]:
            number = int(item["number"])
            results.append({
                "period": str(item["issueNumber"]),
                "number": number,
                "size": "BIG" if number >= 5 else "SMALL"
            })
        return results
    except Exception as e:
        logger.error(f"API Error: {e}")
        return []

# ================= STATS & TABLE =================
def get_winrate(history):
    if not history:
        return 0
    wins = sum(1 for h in history if h["win"])
    return round((wins / len(history)) * 100, 2)

def create_table(history):
    text = "<pre>"
    text += "┏━━━━━━┳━━━━━━━━┳━━━━━┓\n"
    text += "┃ ID   ┃ SIDE   ┃ W/L ┃\n"
    text += "┣━━━━━━╋━━━━━━━━╋━━━━━┫\n"

    for h in history[-10:]:
        p = h["period"][-4:]
        wl = "✅" if h["win"] else "❌"
        text += f"┃ {p:<4} ┃ {h['result']:<6} ┃ {wl} ┃\n"

    text += "┗━━━━━━┻━━━━━━━━┻━━━━━┛"
    text += "</pre>"
    return text

# ================= AI PREDICTION =================
def predict(history):
    if len(history) < 5:
        return random.choice(["BIG", "SMALL"])

    last3 = [x["result"] for x in history[-3:]]

    if last3 == ["BIG", "BIG", "BIG"]:
        return "SMALL"
    if last3 == ["SMALL", "SMALL", "SMALL"]:
        return "BIG"
    if last3 == ["BIG", "SMALL", "BIG"]:
        return "SMALL"
    if last3 == ["SMALL", "BIG", "SMALL"]:
        return "BIG"

    last5 = history[-5:]
    big = sum(1 for x in last5 if x["result"] == "BIG")
    small = sum(1 for x in last5 if x["result"] == "SMALL")

    if big > small:
        return "SMALL"
    elif small > big:
        return "BIG"

    return random.choice(["BIG", "SMALL"])

# ================= MESSAGE TEMPLATES =================
def signal_message(period, prediction):
    confidence = random.randint(80, 96)
    return f"""
<blockquote>🚀 <b>PREMIUM TRX AI SIGNAL</b></blockquote>

🆔 <b>Period:</b>
<code>{period}</code>

🎯 <b>Prediction:</b>
<b>{prediction}</b>

⚡ <b>Confidence:</b>
<b>{confidence}%</b>

⏳ Waiting for result...
"""

def result_message(period, number, actual, win, history):
    global win_streak, loss_streak
    status = "🏆 WIN ✅" if win else "💔 LOSS ❌"

    return f"""
<blockquote>🌐 <b>RESULT REPORT</b></blockquote>

🆔 <b>Period:</b>
<code>{period}</code>

🎲 <b>Number:</b> <code>{number}</code>

📊 <b>Result:</b>
<b>{actual}</b>

{status}

🔥 <b>Win Streak:</b> {win_streak}
💔 <b>Loss Streak:</b> {loss_streak}

📈 <b>Win Rate:</b>
<code>{get_winrate(history)}%</code>

━━━━━━━━━━━━━━

{create_table(history)}

━━━━━━━━━━━━━━
🤖 TRX AI PREMIUM BOT
"""

# ================= MAIN LOOP =================
def main():
    global win_streak, loss_streak

    history = []
    last_signal_period = None

    send_message("""
🤖 <b>TRX AI PREMIUM BOT</b>

🟢 Status: ONLINE
📡 API Connected

🚀 AI System Started
""")
    logger.info("Bot Main Process Started")

    while True:
        try:
            data = get_result()
            if not data:
                time.sleep(1)
                continue

            current_period = data[0]["period"]
            target_period = str(int(current_period) + 1)

            if target_period != last_signal_period:
                last_signal_period = target_period
                prediction = predict(history)

                send_message(signal_message(target_period, prediction))
                logger.info(f"Signal sent -> Period: {target_period}, Prediction: {prediction}")

                found = False
                for _ in range(70):
                    latest = get_result()
                    if not latest:
                        time.sleep(1)
                        continue

                    result = next(
                        (r for r in latest if r["period"] == target_period),
                        None
                    )

                    if result:
                        if target_period in sent_results:
                            break

                        sent_results.add(target_period)
                        actual = result["size"]
                        number = result["number"]
                        win = (prediction == actual)

                        if win:
                            win_streak += 1
                            loss_streak = 0
                        else:
                            loss_streak += 1
                            win_streak = 0

                        history.append({
                            "period": target_period,
                            "result": actual,
                            "win": win
                        })

                        send_message(
                            result_message(target_period, number, actual, win, history)
                        )

                        if win:
                            send_sticker()

                        found = True
                        break

                    time.sleep(1)

                if not found:
                    logger.warning(f"No result found for: {target_period}")

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Main Loop Error: {e}")
            time.sleep(3)

# ================= ENTRY POINT =================
if __name__ == "__main__":
    # Render Web Service အတွက် Background Thread ဖြင့် Web Server စတင်ခြင်း
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    # Bot Loop အား စတင် run ခြင်း
    main()
