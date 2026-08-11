# 日本株取引カレンダー

J-Quants API v2 と JPX の公開 Excel から、決算発表予定日と取引所休場日を取得し、Google カレンダーで購読できる ICS を生成します。

公開カレンダー:

```text
https://botteryosuke.github.io/trading_calendar/japan-all-stocks.ics
```

## セットアップ

`.env.example` を `.env` にコピーし、J-Quants の API キーを設定します。

```env
JQUANTS_API_KEY=your-api-key
```

依存関係の同期と ICS の生成:

```powershell
uv sync
uv run python generate.py
```

生成先はリポジトリ直下の `japan-all-stocks.ics` です。

## J-Quants API v2

- 認証: `x-api-key` ヘッダー
- 決算発表予定日: `GET /v2/fins/earnings-date`
- 取引カレンダー: `GET /v2/markets/calendar`

決算発表予定日 API は `code`、`date`、`scheduled_date` のいずれか1つが必須です。生成処理では、Free プランの 5 req/min 制限を超えないよう直近4取引日を `scheduled_date` で照会し、全決算期・REIT を含む J-Quants データをマージします。遠い将来の予定日は JPX Excel で補完します。

## テスト

```powershell
uv run pytest -q
```

API キーがある場合は実 API を使う統合テストも実行されます。v2 のリクエスト／レスポンス契約はモックテストで常時検証します。
