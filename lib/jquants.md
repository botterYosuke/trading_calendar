# J-Quants API v2 クライアント

`lib/jquants.py` は J-Quants API v2 を `requests` と `pandas` から利用する薄いクライアントです。認証には環境変数 `JQUANTS_API_KEY` を使用し、`x-api-key` ヘッダーとして送信します。v1 の ID トークン取得・リフレッシュは行いません。

## 実装済みエンドポイント

| Python メソッド | J-Quants API v2 | 用途 |
|---|---|---|
| `get_listed_info` | `/v2/equities/master` | 上場銘柄一覧 |
| `get_daily_quotes` | `/v2/equities/bars/daily` | 株価四本値 |
| `get_fins_statements` | `/v2/fins/summary` | 財務情報 |
| `get_fins_announcement` | `/v2/fins/earnings-date` | 全決算期・REITを含む決算発表予定日 |
| `get_market_trading_calendar` | `/v2/markets/calendar` | 取引カレンダー |

レスポンスは `(list[dict], pandas.DataFrame)` で返します。API が `pagination_key` を返した場合は後続ページも取得します。

## 決算発表予定日

公式仕様どおり、次の引数のいずれか1つだけを指定します。

```python
jq.get_fins_announcement(code="86970")
jq.get_fins_announcement(date="2026-08-11")
jq.get_fins_announcement(scheduled_date="2026-08-12")
```

引数なし、または2つ以上の指定は `ValueError` です。

v2 の生フィールド `PubDate`、`SchDate`、`FQName`、`FYE`、`Code`、`CoName`、`CoNameEn` は保持します。ICS 生成用として次の別名も追加します。

| v2 フィールド | 追加する別名 |
|---|---|
| `PubDate` | `PublicationDate` |
| `SchDate` | `Date`, `AnnouncementDate` |
| `CoName` | `CompanyName` |
| `FQName` | `FiscalQuarter` |
| `FYE` | `FiscalYearEnd` |

`SchDate` が空文字のレコードは「未定」のため、ICS イベントにはしません。

`/v2/fins/earnings-date` は日付範囲を受け付けないため、ICS 生成では今日以降の直近4取引日だけを `scheduled_date` で照会します。取引カレンダー取得の1リクエストと合わせて、Free プランの 5 req/min に収めるためです。遠い将来日は JPX Excel のデータを使用し、日次実行のたびに直近範囲を更新します。HTTP 429 を受けた場合は後続日の照会を中止します。

## 取引カレンダー

休日区分のクエリ名は `hol_div`、レスポンス項目は文字列の `HolDiv` です。

| `HolDiv` | 意味 | ICS の休場日イベント |
|---|---|---|
| `0` | 非営業日 | 追加する |
| `1` | 営業日 | 追加しない |
| `2` | 東証半日立会日 | 追加しない |
| `3` | 非営業日（祝日取引あり） | 追加する |

既存コードとの互換用に `holidaydivision=` も受け付けますが、API へは `hol_div` として送信します。

## 公式仕様

- https://jpx-jquants.com/ja/spec
- https://jpx-jquants.com/ja/spec/fin-earnings-date
- https://jpx-jquants.com/ja/spec/mkt-cal
