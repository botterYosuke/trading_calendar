from icalendar import Calendar, Event
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from lib.jquants import jquants
from lib.jpx import JPX
import re
import requests
import pandas as pd


JQUANTS_EARNINGS_REQUEST_LIMIT = 4


def build_event(summary, dt, uid):
    e = Event()
    e.add('summary', summary)
    e.add('dtstart', dt.date())  # date型 = 終日イベント（DTSTART;VALUE=DATE形式）
    e.add('uid', uid)
    e.add('dtstamp', datetime.now(tz=timezone.utc))  # Googleカレンダーで必須
    return e


def _clean_text(value):
    """pandas の NaN/NaT を空文字にし、ICS用の文字列へ正規化する。"""
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def add_announcement_events(c, jq, scheduled_dates=None):
    """決算発表予定日のイベントをカレンダーに追加（J-Quants APIとJPX Excelの両方から取得）"""
    # JPX Excelから取得
    jpx = JPX()
    _, jpx_df = jpx.get_fins_announcement()

    # v2 /fins/earnings-date は銘柄・公表日・発表予定日のいずれかが必須。
    # JPX Excelに含まれる日付と、呼び出し側が指定した直近日付を候補にする。
    query_dates = set(scheduled_dates or [])
    if not jpx_df.empty and "Date" in jpx_df.columns:
        query_dates.update(jpx_df["Date"].dropna().astype(str))

    # Freeプランは5 req/min。先に取得する取引カレンダー1回と合わせるため、
    # 決算予定日は今日以降の直近4日だけを照会する。遠い将来日はJPX Excelで補完する。
    today = datetime.now().strftime("%Y-%m-%d")
    query_dates = sorted(date for date in query_dates if date >= today)[
        :JQUANTS_EARNINGS_REQUEST_LIMIT
    ]

    jq_dataframes = []
    if jq and jq.isEnable:
        for scheduled_date in query_dates:
            _, jq_df = jq.get_fins_announcement(scheduled_date=scheduled_date)
            if not jq_df.empty:
                jq_dataframes.append(jq_df)
            if getattr(jq, "last_status_code", None) == 429:
                break

    # データをマージ
    all_dataframes = []
    all_dataframes.extend(jq_dataframes)
    if not jpx_df.empty:
        all_dataframes.append(jpx_df)

    if all_dataframes:
        # すべてのDataFrameをマージ
        merged_df = pd.concat(all_dataframes, ignore_index=True)
        # 重複を除去（CodeとDateの組み合わせで、詳細なJ-Quantsデータを優先）
        merged_df = merged_df.drop_duplicates(subset=['Code', 'Date'], keep='first')
        announcement_list = merged_df.to_dict(orient='records')
    else:
        announcement_list = []

    # イベントを追加
    for item in announcement_list:
        code = _clean_text(item.get("Code"))
        company_name = _clean_text(item.get("CompanyName"))
        date_str = _clean_text(item.get("Date") or item.get("AnnouncementDate"))

        if date_str:
            try:
                # 日付文字列をdatetimeオブジェクトに変換
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                fiscal_quarter = _clean_text(item.get("FiscalQuarter"))
                fiscal_year = _clean_text(item.get("FiscalYear"))
                fiscal_year_end = _clean_text(item.get("FiscalYearEnd"))

                # イベント名を構築
                summary_parts = [f"[決算] {company_name} ({code})"]
                if fiscal_quarter:
                    summary_parts.append(fiscal_quarter)
                if fiscal_year:
                    summary_parts.append(fiscal_year)
                elif fiscal_year_end:
                    summary_parts.append(fiscal_year_end)
                summary = " ".join(summary_parts)

                uid = f"{code}-announcement-{date_str}"
                c.add_component(build_event(summary, dt, uid))
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
        res = requests.get(f"{jq.API_URL}/v2/markets/calendar", params=params, headers=jq.headers)

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
        # v2 は HolDiv を文字列で返す。旧形式も既存呼び出しとの互換用に受け付ける。
        holiday_division = str(
            item.get("HolDiv", item.get("HolidayDivision", "1"))
        )
        is_trading_day = item.get(
            "IsTradingDay", holiday_division in {"1", "2"}
        )

        # HolDiv=0 は非営業日、3 は非営業日（OSEの祝日取引あり）。
        if date_str and (holiday_division in {"0", "3"} or not is_trading_day):
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                summary = "[休場日] 取引所休場"
                uid = f"holiday-{date_str}"
                c.add_component(build_event(summary, dt, uid))
            except (ValueError, TypeError) as e:
                print(f"日付の解析に失敗しました: {date_str}, エラー: {e}")
                continue


def save_calendar_to_file(c, filepath="japan-all-stocks.ics"):
    """カレンダーをファイルに保存"""
    with open(filepath, "wb") as f:
        f.write(c.to_ical())


def generate_ics(jq):
    """ICSカレンダーファイルを生成"""
    c = Calendar()
    c.add('prodid', '-//Trading Calendar//EN')
    c.add('version', '2.0')

    # 取引カレンダーを取得（休日のみ）
    from_date, to_date = get_date_range(days=365)
    calendar_list, calendar_df = get_trading_calendar_with_retry(jq, from_date, to_date)

    # 新しいv2決算発表予定日APIは日付の完全一致検索のみ対応する。
    # add_announcement_events がこの中から直近4取引日に照会を制限する。
    scheduled_dates = [
        item["Date"]
        for item in calendar_list
        if item.get("Date")
        and str(item.get("HolDiv", item.get("HolidayDivision", "1")))
        in {"1", "2"}
    ]

    # 決算発表予定日のイベントを追加
    add_announcement_events(c, jq, scheduled_dates=scheduled_dates)

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
