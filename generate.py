from ics import Calendar, Event
from datetime import datetime, timedelta
import requests

API_KEY = "YOUR_API_KEY"

def fetch_japan_stock_events():
    # 仮：QUANTX API のエンドポイント
    url = "https://api.quantx.io/v1/japan/events"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def build_event(summary, dt, uid):
    e = Event()
    e.name = summary
    e.begin = dt
    e.uid = uid
    return e

def generate_ics():
    data = fetch_japan_stock_events()

    c = Calendar()

    for item in data:
        ticker = item["ticker"]
        name = item["name"]

        # 決算
        if item.get("earnings_date"):
            dt = item["earnings_date"]
            summary = f"[決算] {name} ({ticker})"
            c.events.add(build_event(summary, dt, f"{ticker}-earnings"))

        # 配当落ち日
        if item.get("ex_dividend_date"):
            dt = item["ex_dividend_date"]
            summary = f"[配当落ち] {name} ({ticker})"
            c.events.add(build_event(summary, dt, f"{ticker}-div-ex"))

        # 配当支払日
        if item.get("dividend_pay_date"):
            dt = item["dividend_pay_date"]
            summary = f"[配当支払] {name} ({ticker})"
            c.events.add(build_event(summary, dt, f"{ticker}-div-pay"))

    with open("japan-all-stocks.ics", "w", encoding="utf-8") as f:
        f.writelines(c)

if __name__ == "__main__":
    generate_ics()
