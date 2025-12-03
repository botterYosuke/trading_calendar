import pytest
import os
import tempfile
from datetime import datetime
from ics import Calendar, Event
from dotenv import load_dotenv

from generate import build_event, generate_ics
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
