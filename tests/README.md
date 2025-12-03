# テスト

このディレクトリには、プロジェクトのテストが含まれています。

## テストの実行

### 環境変数の設定

テストを実行する前に、J-Quants APIの認証情報を環境変数に設定してください。

`.env`ファイルを作成するか、環境変数を設定します：

```env
JQuants_EMAIL_ADDRESS=your_email@example.com
JQuants_PASSWORD=your_password
```

認証情報が設定されていない場合、統合テストは自動的にスキップされます。

### すべてのテストを実行

```powershell
pytest
```

### 詳細な出力でテストを実行

```powershell
pytest -v
```

### カバレッジレポート付きでテストを実行

```powershell
pytest --cov=. --cov-report=html
```

### 特定のテストファイルを実行

```powershell
pytest tests/test_generate.py
```

### 特定のテストクラスを実行

```powershell
pytest tests/test_generate.py::TestBuildEvent
```

### 特定のテストメソッドを実行

```powershell
pytest tests/test_generate.py::TestBuildEvent::test_build_event_basic
```

### 統合テストのみを実行（認証情報が必要）

```powershell
pytest tests/test_generate.py::TestGenerateICS
```

## テストの構成

- `test_generate.py`: `generate.py`の関数のテスト
  - `TestBuildEvent`: `build_event`関数のユニットテスト（認証情報不要）
  - `TestGenerateICS`: `generate_ics`関数の統合テスト（実際のJ-Quants APIを呼び出す）

## テストの種類

### ユニットテスト

- `test_build_event_basic`: 基本的なイベント作成のテスト
- `test_build_event_with_date_only`: 日付のみのイベント作成のテスト

### 統合テスト（実際のAPIを呼び出す）

- `test_jquants_api_connection`: J-Quants APIへの接続テスト
- `test_get_fins_announcement`: 決算発表予定日の取得テスト
- `test_get_market_trading_calendar`: 取引カレンダーの取得テスト
- `test_generate_ics_with_real_api`: 実際のAPIを使用したICS生成のテスト
- `test_generate_ics_contains_announcements`: ICSファイルに決算発表予定日が含まれることを確認
- `test_generate_ics_contains_holidays`: ICSファイルに休場日が含まれることを確認
- `test_generate_ics_event_format`: ICSファイルのイベント形式が正しいことを確認

## 注意事項

- **統合テストは実際のJ-Quants APIを呼び出します**
- 認証情報が設定されていない場合、統合テストは自動的にスキップされます
- テストを実行する前に、必要な依存関係がインストールされていることを確認してください
- 統合テストは一時ファイルを使用するため、テスト実行後に自動的にクリーンアップされます

