from ics import Calendar, Event
from datetime import datetime, timedelta
from dotenv import load_dotenv
from lib.jquants import jquants
from lib.jpx import JPX
import re
import requests
import pandas as pd

def build_event(summary, dt, uid):
    e = Event()
    e.name = summary
    e.begin = dt
    e.uid = uid
    return e


def add_announcement_events(c, jq):
    """決算発表予定日のイベントをカレンダーに追加（J-Quants APIとJPX Excelの両方から取得）"""
    # J-Quants APIから取得
    jq_list, jq_df = jq.get_fins_announcement() if jq and jq.isEnable else ([], pd.DataFrame())
    
    # JPX Excelから取得
    jpx = JPX()
    jpx_list, jpx_df = jpx.get_fins_announcement()
    
    # データをマージ
    all_dataframes = []
    if not jq_df.empty:
        all_dataframes.append(jq_df)
    if not jpx_df.empty:
        all_dataframes.append(jpx_df)
    
    if all_dataframes:
        # すべてのDataFrameをマージ
        merged_df = pd.concat(all_dataframes, ignore_index=True)
        # 重複を除去（CodeとDateの組み合わせで、JPX Excelのデータを優先）
        merged_df = merged_df.drop_duplicates(subset=['Code', 'Date'], keep='first')
        announcement_list = merged_df.to_dict(orient='records')
    else:
        announcement_list = []
    
    # イベントを追加
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


def get_date_range(days=365):
    """日付範囲を取得（デフォルトは未来365日間）"""
    today = datetime.now()
    from_date = today.strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=days)).strftime("%Y-%m-%d")
    return from_date, to_date


def extract_subscription_period(error_message):
    """エラーメッセージからサブスクリプション期間を抽出"""
    date_range_pattern = r'(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})'
    match = re.search(date_range_pattern, error_message)
    
    if match:
        subscription_from = match.group(1)
        subscription_to = match.group(2)
        return subscription_from, subscription_to
    return None, None


def get_trading_calendar_with_retry(jq, from_date, to_date):
    """取引カレンダーを取得（エラー時はサブスクリプション期間を抽出して再試行）"""
    calendar_list, calendar_df = jq.get_market_trading_calendar(from_=from_date, to=to_date)
    
    # エラーが発生した場合（空のリストが返された場合）、エラーメッセージから期間を抽出して再試行
    if not calendar_list:
        # エラーメッセージを取得するために直接APIを呼び出す
        params = {"from": from_date, "to": to_date}
        res = requests.get(f"{jq.API_URL}/v1/markets/trading_calendar", params=params, headers=jq.headers)
        
        if res.status_code != 200:
            error_data = res.json()
            error_message = error_data.get("message", "")
            
            subscription_from, subscription_to = extract_subscription_period(error_message)
            
            if subscription_from and subscription_to:
                print(f"サブスクリプション期間を検出しました: {subscription_from} ~ {subscription_to}")
                print(f"この期間内で再度取得を試みます...")
                
                # サブスクリプション期間内で再度取得
                calendar_list, calendar_df = jq.get_market_trading_calendar(from_=subscription_from, to=subscription_to)
            else:
                print(f"エラーメッセージから期間を抽出できませんでした: {error_message}")
    
    return calendar_list, calendar_df


def add_holiday_events(c, calendar_list):
    """休場日のイベントをカレンダーに追加"""
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


def save_calendar_to_file(c, filepath="japan-all-stocks.ics"):
    """カレンダーをファイルに保存"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(str(c))


def generate_ics(jq):
    """ICSカレンダーファイルを生成"""
    c = Calendar()
    
    # 決算発表予定日のイベントを追加
    add_announcement_events(c, jq)
    
    # 取引カレンダーを取得（休日のみ）
    from_date, to_date = get_date_range(days=365)
    calendar_list, calendar_df = get_trading_calendar_with_retry(jq, from_date, to_date)
    
    # 休場日のイベントを追加
    add_holiday_events(c, calendar_list)
    
    # カレンダーをファイルに保存
    save_calendar_to_file(c)

if __name__ == "__main__":
    # 環境変数を読み込み
    load_dotenv()

    # 1) 準備
    jq = jquants()
    if not jq.isEnable:
        print("J-Quants apiの準備ができませんでした")
        exit()

    generate_ics(jq)
