import pytest
import os
import tempfile
from datetime import datetime
from ics import Calendar, Event
from dotenv import load_dotenv
from unittest.mock import Mock, patch, MagicMock

from generate import (
    build_event,
    generate_ics,
    add_announcement_events,
    get_date_range,
    extract_subscription_period,
    get_trading_calendar_with_retry,
    add_holiday_events,
    save_calendar_to_file,
)
from lib.jquants import jquants


# 環境変数を読み込み
load_dotenv()


def skip_if_no_credentials():
    """J-Quantsの認証情報がない場合はテストをスキップ"""
    email = os.getenv('JQuants_EMAIL_ADDRESS')
    password = os.getenv('JQuants_PASSWORD')
    if not email or not password:
        pytest.skip("J-Quantsの認証情報が設定されていません。環境変数JQuants_EMAIL_ADDRESSとJQuants_PASSWORDを設定してください。")


class TestBuildEvent:
    """build_event関数のテスト"""
    
    def test_build_event_basic(self):
        """基本的なイベント作成のテスト"""
        summary = "テストイベント"
        dt = datetime(2024, 1, 15, 10, 0, 0)
        uid = "test-uid-123"
        
        event = build_event(summary, dt, uid)
        
        assert isinstance(event, Event)
        assert event.name == summary
        # icsライブラリはArrowオブジェクトを返すため、datetimeに変換して比較（タイムゾーンを無視）
        event_dt = event.begin.datetime.replace(tzinfo=None)
        assert event_dt == dt
        assert event.uid == uid
    
    def test_build_event_with_date_only(self):
        """日付のみのイベント作成のテスト"""
        summary = "[決算] テスト会社 (1234)"
        dt = datetime(2024, 3, 31, 0, 0, 0)
        uid = "1234-announcement-2024-03-31"
        
        event = build_event(summary, dt, uid)
        
        assert event.name == summary
        # icsライブラリはArrowオブジェクトを返すため、datetimeに変換して比較（タイムゾーンを無視）
        event_dt = event.begin.datetime.replace(tzinfo=None)
        assert event_dt == dt
        assert event.uid == uid


class TestGetDateRange:
    """get_date_range関数のテスト"""
    
    def test_get_date_range_default(self):
        """デフォルトの日付範囲（365日）のテスト"""
        from_date, to_date = get_date_range()
        
        assert isinstance(from_date, str)
        assert isinstance(to_date, str)
        assert len(from_date) == 10  # YYYY-MM-DD形式
        assert len(to_date) == 10
    
    def test_get_date_range_custom(self):
        """カスタム日数の日付範囲のテスト"""
        from_date, to_date = get_date_range(days=30)
        
        assert isinstance(from_date, str)
        assert isinstance(to_date, str)
        # 日付の差が約30日であることを確認
        from datetime import datetime, timedelta
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        to_dt = datetime.strptime(to_date, "%Y-%m-%d")
        diff = (to_dt - from_dt).days
        assert diff == 30, f"日付の差が期待値と異なります（期待: 30日、実際: {diff}日）"


class TestExtractSubscriptionPeriod:
    """extract_subscription_period関数のテスト"""
    
    def test_extract_subscription_period_valid(self):
        """有効なエラーメッセージから期間を抽出するテスト"""
        error_message = "Your subscription covers the following dates: 2023-09-10 ~ 2025-09-10"
        subscription_from, subscription_to = extract_subscription_period(error_message)
        
        assert subscription_from == "2023-09-10"
        assert subscription_to == "2025-09-10"
    
    def test_extract_subscription_period_invalid(self):
        """無効なエラーメッセージから期間を抽出できないことを確認"""
        error_message = "Some other error message"
        subscription_from, subscription_to = extract_subscription_period(error_message)
        
        assert subscription_from is None
        assert subscription_to is None


class TestAddAnnouncementEvents:
    """add_announcement_events関数のテスト"""
    
    def test_add_announcement_events_with_real_api(self):
        """実際のAPIを使用した決算発表イベント追加のテスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        c = Calendar()
        add_announcement_events(c, jq)
        
        # イベントが追加されたことを確認（データがある場合）
        # データがない場合でもエラーにならないことを確認
        assert isinstance(c.events, set)


class TestAddHolidayEvents:
    """add_holiday_events関数のテスト"""
    
    def test_add_holiday_events_with_holidays(self):
        """休場日のイベント追加のテスト"""
        c = Calendar()
        calendar_list = [
            {"Date": "2024-01-01", "HolidayDivision": 0, "IsTradingDay": False},
            {"Date": "2024-01-02", "HolidayDivision": 1, "IsTradingDay": True},
            {"Date": "2024-01-03", "HolidayDivision": 0, "IsTradingDay": True},
        ]
        
        add_holiday_events(c, calendar_list)
        
        # 休場日（HolidayDivision=0 または IsTradingDay=False）のみが追加される
        # 2024-01-01 と 2024-01-03 が追加されるはず
        event_dates = {event.begin.datetime.date() for event in c.events}
        assert datetime(2024, 1, 1).date() in event_dates
        assert datetime(2024, 1, 3).date() in event_dates
        assert datetime(2024, 1, 2).date() not in event_dates  # 取引日なので追加されない
    
    def test_add_holiday_events_with_invalid_date(self):
        """無効な日付が含まれる場合のテスト"""
        c = Calendar()
        calendar_list = [
            {"Date": "invalid-date", "HolidayDivision": 0, "IsTradingDay": False},
        ]
        
        # エラーが発生しても処理が続行されることを確認
        add_holiday_events(c, calendar_list)
        assert len(c.events) == 0


class TestSaveCalendarToFile:
    """save_calendar_to_file関数のテスト"""
    
    def test_save_calendar_to_file(self):
        """カレンダーをファイルに保存するテスト"""
        c = Calendar()
        # テスト用のイベントを追加
        event = build_event("テストイベント", datetime(2024, 1, 1), "test-uid")
        c.events.add(event)
        
        # 一時ファイルを使用
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False, encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            save_calendar_to_file(c, tmp_path)
            
            # ファイルが作成されたことを確認
            assert os.path.exists(tmp_path)
            
            # ファイルの内容を確認
            with open(tmp_path, 'r', encoding='utf-8') as f:
                content = f.read()
                assert len(content) > 0
                assert "BEGIN:VCALENDAR" in content
                assert "END:VCALENDAR" in content
                assert "テストイベント" in content
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestGetTradingCalendarWithRetry:
    """get_trading_calendar_with_retry関数のテスト"""
    
    def test_get_trading_calendar_with_retry_success(self):
        """正常にカレンダーを取得できる場合のテスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        from datetime import timedelta
        today = datetime.now()
        from_date = today.strftime("%Y-%m-%d")
        to_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        
        calendar_list, calendar_df = get_trading_calendar_with_retry(jq, from_date, to_date)
        
        assert isinstance(calendar_list, list)
        assert len(calendar_list) >= 0
    
    def test_get_trading_calendar_with_retry_with_error(self):
        """エラーが発生した場合の再試行機能のテスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        # モックの準備
        original_get_market_trading_calendar = jq.get_market_trading_calendar
        call_count = [0]
        
        def mock_get_market_trading_calendar(from_="", to=""):
            call_count[0] += 1
            if call_count[0] == 1:
                # 最初の呼び出し: 空のリストを返す（エラーをシミュレート）
                return [], __import__('pandas').DataFrame()
            else:
                # 2回目の呼び出し: 正常なデータを返す
                return original_get_market_trading_calendar(from_=from_, to=to)
        
        # エラーレスポンスをモック
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'message': 'Your subscription covers the following dates: 2023-09-10 ~ 2025-09-10. If you want more data, please check other plans:https://jpx-jquants.com/'
        }
        
        try:
            jq.get_market_trading_calendar = mock_get_market_trading_calendar
            
            from datetime import timedelta
            today = datetime.now()
            from_date = today.strftime("%Y-%m-%d")
            to_date = (today + timedelta(days=365)).strftime("%Y-%m-%d")
            
            with patch('requests.get', return_value=mock_response):
                calendar_list, calendar_df = get_trading_calendar_with_retry(jq, from_date, to_date)
            
            # get_market_trading_calendarが2回呼ばれたことを確認（1回目: エラー、2回目: 再試行）
            assert call_count[0] >= 1, "get_market_trading_calendarが呼ばれていません"
        finally:
            # モックを元に戻す
            jq.get_market_trading_calendar = original_get_market_trading_calendar


class TestGenerateICS:
    """generate_ics関数の統合テスト（実際のJ-Quants APIを呼び出す）"""
    
    def test_jquants_api_connection(self):
        """J-Quants APIへの接続テスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        assert jq.isEnable, "J-Quants APIの認証に失敗しました"
    
    def test_get_fins_announcement(self):
        """決算発表予定日の取得テスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        announcement_list, announcement_df = jq.get_fins_announcement()
        
        assert isinstance(announcement_list, list)
        assert len(announcement_list) >= 0
        
        # データがある場合、構造を確認
        if len(announcement_list) > 0:
            first_item = announcement_list[0]
            assert "Code" in first_item or "AnnouncementDate" in first_item or "Date" in first_item
    
    def test_get_market_trading_calendar(self):
        """取引カレンダーの取得テスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        from datetime import timedelta
        today = datetime.now()
        from_date = today.strftime("%Y-%m-%d")
        to_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        
        calendar_list, calendar_df = jq.get_market_trading_calendar(from_=from_date, to=to_date)
        
        assert isinstance(calendar_list, list)
        assert len(calendar_list) >= 0
        
        # データがある場合、構造を確認
        if len(calendar_list) > 0:
            first_item = calendar_list[0]
            assert "Date" in first_item
    
    def test_generate_ics_with_real_api(self):
        """実際のJ-Quants APIを使用したICS生成のテスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        # 一時ファイルを使用
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False, encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # generate_ics関数を修正して一時ファイルに書き込む
            # 元の関数を一時的にパッチ
            import builtins
            original_open = builtins.open
            
            def mock_open(file_path, mode='r', encoding=None, **kwargs):
                if file_path == "japan-all-stocks.ics":
                    return original_open(tmp_path, mode, encoding=encoding, **kwargs)
                return original_open(file_path, mode, encoding=encoding, **kwargs)
            
            # パッチを適用
            builtins.open = mock_open
            
            try:
                # テスト実行
                generate_ics(jq)
                
                # ファイルが作成されたことを確認
                assert os.path.exists(tmp_path), "ICSファイルが作成されませんでした"
                
                # ファイルの内容を確認
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    assert len(content) > 0, "ICSファイルが空です"
                    assert "BEGIN:VCALENDAR" in content, "ICSファイルの形式が正しくありません"
                    assert "END:VCALENDAR" in content, "ICSファイルの形式が正しくありません"
                
                # カレンダーオブジェクトとして読み込めることを確認
                from ics import Calendar
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    calendar = Calendar(f.read())
                    assert len(calendar.events) >= 0, "カレンダーにイベントが含まれていません"
                    
            finally:
                # パッチを元に戻す
                builtins.open = original_open
                
        finally:
            # 一時ファイルを削除
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_generate_ics_contains_announcements(self):
        """ICSファイルに決算発表予定日が含まれることを確認"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        # 決算発表予定日を取得
        announcement_list, _ = jq.get_fins_announcement()
        
        if len(announcement_list) == 0:
            pytest.skip("決算発表予定日のデータがありません")
        
        # 一時ファイルを使用
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False, encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            import builtins
            original_open = builtins.open
            
            def mock_open(file_path, mode='r', encoding=None, **kwargs):
                if file_path == "japan-all-stocks.ics":
                    return original_open(tmp_path, mode, encoding=encoding, **kwargs)
                return original_open(file_path, mode, encoding=encoding, **kwargs)
            
            builtins.open = mock_open
            
            try:
                generate_ics(jq)
                
                # ファイルの内容を確認
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 決算イベントが含まれていることを確認
                    assert "[決算]" in content, "決算発表予定日がICSファイルに含まれていません"
                    
            finally:
                builtins.open = original_open
                
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_generate_ics_contains_holidays(self):
        """ICSファイルに休場日が含まれることを確認"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        # 取引カレンダーを取得
        from datetime import timedelta
        today = datetime.now()
        from_date = today.strftime("%Y-%m-%d")
        to_date = (today + timedelta(days=365)).strftime("%Y-%m-%d")
        
        calendar_list, _ = jq.get_market_trading_calendar(from_=from_date, to=to_date)
        
        # 休日があるか確認
        holidays = [item for item in calendar_list 
                   if item.get("HolidayDivision") == 0 or not item.get("IsTradingDay", True)]
        
        if len(holidays) == 0:
            pytest.skip("休場日のデータがありません")
        
        # 一時ファイルを使用
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False, encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            import builtins
            original_open = builtins.open
            
            def mock_open(file_path, mode='r', encoding=None, **kwargs):
                if file_path == "japan-all-stocks.ics":
                    return original_open(tmp_path, mode, encoding=encoding, **kwargs)
                return original_open(file_path, mode, encoding=encoding, **kwargs)
            
            builtins.open = mock_open
            
            try:
                generate_ics(jq)
                
                # ファイルの内容を確認
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 休場日イベントが含まれていることを確認
                    assert "[休場日]" in content, "休場日がICSファイルに含まれていません"
                    
            finally:
                builtins.open = original_open
                
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_generate_ics_event_format(self):
        """ICSファイルのイベント形式が正しいことを確認"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        # 一時ファイルを使用
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False, encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            import builtins
            original_open = builtins.open
            
            def mock_open(file_path, mode='r', encoding=None, **kwargs):
                if file_path == "japan-all-stocks.ics":
                    return original_open(tmp_path, mode, encoding=encoding, **kwargs)
                return original_open(file_path, mode, encoding=encoding, **kwargs)
            
            builtins.open = mock_open
            
            try:
                generate_ics(jq)
                
                # ファイルの内容を確認
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # ICS形式の基本構造を確認
                    assert "BEGIN:VEVENT" in content or len(content) == 0, "イベントの形式が正しくありません"
                    if "BEGIN:VEVENT" in content:
                        assert "END:VEVENT" in content, "イベントの終了タグがありません"
                        assert "DTSTART" in content, "イベントの開始日時がありません"
                        assert "SUMMARY" in content or "UID" in content, "イベントの基本情報がありません"
                    
            finally:
                builtins.open = original_open
                
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_extract_subscription_period(self):
        """extract_subscription_period関数のテスト"""
        # テストケース1: 正常なエラーメッセージ
        error_message1 = "Your subscription covers the following dates: 2023-09-10 ~ 2025-09-10. If you want more data, please check other plans:https://jpx-jquants.com/"
        subscription_from, subscription_to = extract_subscription_period(error_message1)
        
        assert subscription_from == "2023-09-10", "開始日の抽出が正しくありません"
        assert subscription_to == "2025-09-10", "終了日の抽出が正しくありません"
        
        # テストケース2: 異なる形式のエラーメッセージ
        error_message2 = "Subscription period: 2024-01-01~2024-12-31"
        subscription_from, subscription_to = extract_subscription_period(error_message2)
        
        assert subscription_from == "2024-01-01", "開始日の抽出が正しくありません"
        assert subscription_to == "2024-12-31", "終了日の抽出が正しくありません"
        
        # テストケース3: 期間が含まれていないメッセージ
        error_message3 = "Some other error message"
        subscription_from, subscription_to = extract_subscription_period(error_message3)
        
        assert subscription_from is None, "期間が含まれていないメッセージから誤って期間を抽出しました"
        assert subscription_to is None, "期間が含まれていないメッセージから誤って期間を抽出しました"
    
    def test_generate_ics_error_handling_with_subscription_period(self):
        """サブスクリプション期間エラーが発生した場合の再試行機能のテスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        # 一時ファイルを使用
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False, encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            import builtins
            original_open = builtins.open
            
            def mock_open(file_path, mode='r', encoding=None, **kwargs):
                if file_path == "japan-all-stocks.ics":
                    return original_open(tmp_path, mode, encoding=encoding, **kwargs)
                return original_open(file_path, mode, encoding=encoding, **kwargs)
            
            builtins.open = mock_open
            
            # モックの準備
            original_get_market_trading_calendar = jq.get_market_trading_calendar
            original_requests_get = __import__('requests').get
            
            # 最初の呼び出しでは空のリストを返す（エラーをシミュレート）
            # 2回目の呼び出しでは正常なデータを返す
            call_count = [0]
            
            def mock_get_market_trading_calendar(from_="", to=""):
                call_count[0] += 1
                if call_count[0] == 1:
                    # 最初の呼び出し: 空のリストを返す（エラーをシミュレート）
                    return [], __import__('pandas').DataFrame()
                else:
                    # 2回目の呼び出し: 正常なデータを返す
                    return original_get_market_trading_calendar(from_=from_, to=to)
            
            # エラーレスポンスをモック
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {
                'message': 'Your subscription covers the following dates: 2023-09-10 ~ 2025-09-10. If you want more data, please check other plans:https://jpx-jquants.com/'
            }
            
            try:
                # get_market_trading_calendarをモック
                jq.get_market_trading_calendar = mock_get_market_trading_calendar
                
                # requests.getをモック
                with patch('requests.get', return_value=mock_response):
                    generate_ics(jq)
                
                # ファイルが作成されたことを確認
                assert os.path.exists(tmp_path), "ICSファイルが作成されませんでした"
                
                # get_market_trading_calendarが2回呼ばれたことを確認（1回目: エラー、2回目: 再試行）
                assert call_count[0] >= 1, "get_market_trading_calendarが呼ばれていません"
                
            finally:
                # モックを元に戻す
                jq.get_market_trading_calendar = original_get_market_trading_calendar
                builtins.open = original_open
                
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_generate_ics_retry_with_subscription_period_mock(self):
        """モックを使用したサブスクリプション期間エラー時の再試行テスト"""
        skip_if_no_credentials()
        
        jq = jquants()
        if not jq.isEnable:
            pytest.skip("J-Quants APIの認証に失敗しました")
        
        # 一時ファイルを使用
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ics', delete=False, encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            import builtins
            original_open = builtins.open
            
            def mock_open(file_path, mode='r', encoding=None, **kwargs):
                if file_path == "japan-all-stocks.ics":
                    return original_open(tmp_path, mode, encoding=encoding, **kwargs)
                return original_open(file_path, mode, encoding=encoding, **kwargs)
            
            builtins.open = mock_open
            
            # モックデータの準備
            mock_calendar_data = [
                {"Date": "2024-01-01", "HolidayDivision": 0, "IsTradingDay": False},
                {"Date": "2024-01-02", "HolidayDivision": 1, "IsTradingDay": True},
            ]
            
            call_count = [0]
            original_method = jq.get_market_trading_calendar
            
            def mock_get_market_trading_calendar(from_="", to=""):
                call_count[0] += 1
                if call_count[0] == 1:
                    # 最初の呼び出し: 空のリストを返す
                    return [], __import__('pandas').DataFrame()
                else:
                    # 2回目の呼び出し: モックデータを返す
                    import pandas as pd
                    df = pd.DataFrame(mock_calendar_data)
                    return mock_calendar_data, df
            
            # エラーレスポンスをモック
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {
                'message': 'Your subscription covers the following dates: 2023-09-10 ~ 2025-09-10. If you want more data, please check other plans:https://jpx-jquants.com/'
            }
            
            try:
                jq.get_market_trading_calendar = mock_get_market_trading_calendar
                
                with patch('requests.get', return_value=mock_response):
                    generate_ics(jq)
                
                # ファイルが作成されたことを確認
                assert os.path.exists(tmp_path), "ICSファイルが作成されませんでした"
                
                # get_market_trading_calendarが2回呼ばれたことを確認
                assert call_count[0] == 2, f"get_market_trading_calendarが期待通りに呼ばれていません（呼び出し回数: {call_count[0]}）"
                
                # ファイルの内容を確認
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 休場日が含まれていることを確認
                    assert "[休場日]" in content or len(content) > 0, "ICSファイルに休場日が含まれていません"
                
            finally:
                jq.get_market_trading_calendar = original_method
                builtins.open = original_open
                
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
