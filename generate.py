from ics import Calendar, Event
from datetime import datetime, timedelta
from dotenv import load_dotenv
from lib.jquants import jquants

def build_event(summary, dt, uid):
    e = Event()
    e.name = summary
    e.begin = dt
    e.uid = uid
    return e

def generate_ics(jq):
    c = Calendar()

    # 決算発表予定日を取得
    announcement_list, announcement_df = jq.get_fins_announcement()
    
    for item in announcement_list:
        code = item.get("Code", "")
        company_name = item.get("CompanyName", "")
        date_str = item.get("Date") or item.get("AnnouncementDate", "")
        
        if date_str:
            try:
                # 日付文字列をdatetimeオブジェクトに変換
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                fiscal_quarter = item.get("FiscalQuarter", "")
                fiscal_year = item.get("FiscalYear", "")
                
                # イベント名を構築
                summary_parts = [f"[決算] {company_name} ({code})"]
                if fiscal_quarter:
                    summary_parts.append(fiscal_quarter)
                if fiscal_year:
                    summary_parts.append(fiscal_year)
                summary = " ".join(summary_parts)
                
                uid = f"{code}-announcement-{date_str}"
                c.events.add(build_event(summary, dt, uid))
            except (ValueError, TypeError) as e:
                print(f"日付の解析に失敗しました: {date_str}, エラー: {e}")
                continue

    # 取引カレンダーを取得（休日のみ）
    # 未来1年間のデータを取得
    today = datetime.now()
    from_date = today.strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=365)).strftime("%Y-%m-%d")
    
    calendar_list, calendar_df = jq.get_market_trading_calendar(from_=from_date, to=to_date)
    
    for item in calendar_list:
        date_str = item.get("Date", "")
        holiday_division = item.get("HolidayDivision", 1)
        is_trading_day = item.get("IsTradingDay", True)
        
        # 休日（HolidayDivision=0 または IsTradingDay=False）の場合のみイベントを追加
        if date_str and (holiday_division == 0 or not is_trading_day):
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                summary = "[休場日] 取引所休場"
                uid = f"holiday-{date_str}"
                c.events.add(build_event(summary, dt, uid))
            except (ValueError, TypeError) as e:
                print(f"日付の解析に失敗しました: {date_str}, エラー: {e}")
                continue

    with open("japan-all-stocks.ics", "w", encoding="utf-8") as f:
        f.write(str(c))

if __name__ == "__main__":
    # 環境変数を読み込み
    load_dotenv()

    # 1) 準備
    jq = jquants()
    if not jq.isEnable:
        print("J-Quants apiの準備ができませんでした")
        exit()

    generate_ics(jq)
