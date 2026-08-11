# テスト

すべてのテストを実行します。

```powershell
uv run pytest -q
```

J-Quants の実 API を使う統合テストを有効にする場合は、`.env` に API キーを設定します。

```env
JQUANTS_API_KEY=your-api-key
```

API キーがない環境では統合テストだけがスキップされます。

## 構成

- `test_generate.py`: ICS 生成、JPX 連携、実 API の統合テスト
- `test_jquants_v2.py`: API キー認証、v2 エンドポイント、必須クエリ、ページング、`HolDiv` と ICS 変換のモックテスト

v2 契約テストだけを実行する場合:

```powershell
uv run pytest -q tests/test_jquants_v2.py
```
