from typing import Tuple
import requests
import os
from datetime import datetime
import pandas as pd
import logging
import threading

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class jquants:
    """
    J-Quants API Client (Singleton)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(jquants, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 既に初期化済みの場合はスキップ
        if hasattr(self, "_initialized"):
            return

        self.API_URL = "https://api.jquants.com"
        self.api_key = os.getenv("JQUANTS_API_KEY")
        self.headers = {}
        self.last_status_code = None
        self._initialized = True
        self.isEnable = False

        if self.api_key:
            self.headers = {"x-api-key": self.api_key}
            self.isEnable = True
            logger.info("API使用の準備が完了しました。")
        else:
            logger.warning(
                "J-QuantsのAPIキー(JQUANTS_API_KEY)が環境変数に設定されていません。"
            )

    def _refresh_token_if_needed(self) -> bool:
        """
        V2APIではトークンリフレッシュは不要なため、常にTrueを返す
        """
        return True

    def get_listed_info(self, code="", date="") -> Tuple[list, pd.DataFrame]:
        """
        上場銘柄一覧（/v2/equities/master）

        - 過去時点での銘柄情報、当日の銘柄情報および翌営業日時点の銘柄情報が取得可能です。
        - データの取得では、銘柄コード（code）または日付（date）の指定が可能です。

        （データ更新時刻）
        - 毎営業日の24:00頃

        """
        # トークンリフレッシュが必要かチェック（V2では何もしない）
        self._refresh_token_if_needed()

        params = {}
        if code != "":
            params["code"] = code
        if date != "":
            params["date"] = date

        res = requests.get(
            f"{self.API_URL}/v2/equities/master", params=params, headers=self.headers
        )
        if res.status_code == 200:
            d = res.json()
            data = d.get("data", [])
            while d.get("pagination_key"):
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(
                    f"{self.API_URL}/v2/equities/master",
                    params=params,
                    headers=self.headers,
                )
                d = res.json()
                data += d.get("data", [])

            df = pd.DataFrame(data)
            if not df.empty:
                df["source"] = "j-quants"
                res = df.to_dict(orient="records")
                return res, df
            else:
                return [], pd.DataFrame()

        logger.error(f"API Error: {res.status_code} - {res.text}")
        return [], pd.DataFrame()

    def get_daily_quotes(
        self, code: str, from_: datetime = None, to: datetime = None
    ) -> Tuple[list, pd.DataFrame]:
        """
        株価四本値（/v2/equities/bars/daily）

        - 株価は分割・併合を考慮した調整済み株価（小数点第２位四捨五入）と調整前の株価を取得することができます。
        - データの取得では、銘柄コード（code）または日付（date）の指定が必須となります。

        （データ更新時刻）
        - 毎営業日の17:00頃

        - Premiumプランの方には、日通しに加え、前場(Morning)及び後場(Afternoon)の四本値及び取引高（調整前・後両方）・取引代金が取得可能です。
        - データの取得では、日付（date）を指定して全銘柄取得するモードがあるが、非対応となっています。
        """
        # トークンリフレッシュが必要かチェック（V2では何もしない）
        self._refresh_token_if_needed()

        params = {}
        if code != "":
            params["code"] = code
        if from_ is not None:
            params["from"] = from_.strftime("%Y-%m-%d")
        if to is not None:
            params["to"] = to.strftime("%Y-%m-%d")

        res = requests.get(
            f"{self.API_URL}/v2/equities/bars/daily",
            params=params,
            headers=self.headers,
        )
        if res.status_code == 200:
            d = res.json()
            data = d.get("data", [])
            while d.get("pagination_key"):
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(
                    f"{self.API_URL}/v2/equities/bars/daily",
                    params=params,
                    headers=self.headers,
                )
                d = res.json()
                data += d.get("data", [])

            df = pd.DataFrame(data)
            if not df.empty:
                # 型変換（日次株価フィールド定義に基づく） - V2のカラム名短縮の補完もここで行う
                df = _normalize_columns(df)
                df["source"] = "j-quants"
                res = df.to_dict(orient="records")
                return res, df
            else:
                return [], pd.DataFrame()

        logger.error(f"API Error: {res.status_code} - {res.text}")
        return [], pd.DataFrame()

    def get_fins_statements(
        self, code="", date="", from_="", to=""
    ) -> Tuple[list, pd.DataFrame]:
        """
        財務情報（/v2/fins/summary）

        - 財務情報APIでは、上場企業がTDnetへ提出する決算短信Summary等を基に作成された、四半期毎の財務情報を取得することができます。
        - データの取得では、銘柄コード（code）または開示日（date）の指定が必須です。

        （データ更新時刻）
        - 速報18:00頃、確報24:30頃
        """
        # トークンリフレッシュが必要かチェック（V2では何もしない）
        self._refresh_token_if_needed()

        params = {}
        if code != "":
            params["code"] = code
        if date != "":
            params["date"] = date
        if from_ != "":
            params["from"] = from_
        if to != "":
            params["to"] = to

        res = requests.get(
            f"{self.API_URL}/v2/fins/summary", params=params, headers=self.headers
        )
        if res.status_code == 200:
            d = res.json()
            data = d.get("data", [])
            while d.get("pagination_key"):
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(
                    f"{self.API_URL}/v2/fins/summary",
                    params=params,
                    headers=self.headers,
                )
                d = res.json()
                data += d.get("data", [])

            df = pd.DataFrame(data)
            if not df.empty:
                df["source"] = "j-quants"
                res = df.to_dict(orient="records")
                return res, df
            else:
                return [], pd.DataFrame()

        logger.error(f"API Error: {res.status_code} - {res.text}")
        return [], pd.DataFrame()

    def get_fins_announcement(
        self, code="", date="", scheduled_date=""
    ) -> Tuple[list, pd.DataFrame]:
        """
        決算発表予定日（/v2/fins/earnings-date）

        code（銘柄コード）、date（公表日）、scheduled_date（発表予定日）の
        いずれか1つの指定が必須です。2つ以上を同時に指定することはできません。
        """
        self._refresh_token_if_needed()

        filters = {
            "code": code,
            "date": date,
            "scheduled_date": scheduled_date,
        }
        params = {key: value for key, value in filters.items() if value != ""}
        if len(params) != 1:
            raise ValueError(
                "code, date, scheduled_date のいずれか1つを指定してください"
            )

        res = requests.get(
            f"{self.API_URL}/v2/fins/earnings-date",
            params=params,
            headers=self.headers,
        )
        self.last_status_code = res.status_code
        if res.status_code == 200:
            d = res.json()
            data = d.get("data", [])
            while d.get("pagination_key"):
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(
                    f"{self.API_URL}/v2/fins/earnings-date",
                    params=params,
                    headers=self.headers,
                )
                self.last_status_code = res.status_code
                if res.status_code != 200:
                    logger.error(f"API Error: {res.status_code} - {res.text}")
                    return [], pd.DataFrame()
                d = res.json()
                data += d.get("data", [])

            df = pd.DataFrame(data)
            if not df.empty:
                # ICS生成コードが利用するドメイン名を追加しつつ、v2の生フィールドも残す。
                df["PublicationDate"] = df["PubDate"]
                df["Date"] = df["SchDate"]
                df["AnnouncementDate"] = df["SchDate"]
                df["CompanyName"] = df["CoName"]
                df["FiscalQuarter"] = df["FQName"]
                df["FiscalYearEnd"] = df["FYE"]
                df["source"] = "j-quants"
                res = df.to_dict(orient="records")
                return res, df
            else:
                return [], pd.DataFrame()

        logger.error(f"API Error: {res.status_code} - {res.text}")
        return [], pd.DataFrame()

    def get_market_trading_calendar(
        self, holidaydivision="", from_="", to="", hol_div=""
    ) -> Tuple[list, pd.DataFrame]:
        """
        取引カレンダー（/v2/markets/calendar）

        - 東証およびOSEにおける営業日、休業日、ならびにOSEにおける祝日取引の有無の情報を取得できます。
        - データの取得では、休日区分（hol_div）または日付（from/to）の指定が可能です。

        （データ更新日）
        - 不定期（原則として、毎年2月頃をめどに翌年1年間の営業日および祝日取引実施日（予定）を更新します。）
        """
        # トークンリフレッシュが必要かチェック（V2では何もしない）
        self._refresh_token_if_needed()

        params = {}
        holiday_filter = hol_div or holidaydivision
        if holiday_filter != "":
            params["hol_div"] = holiday_filter
        if from_ != "":
            params["from"] = from_
        if to != "":
            params["to"] = to

        res = requests.get(
            f"{self.API_URL}/v2/markets/calendar", params=params, headers=self.headers
        )
        if res.status_code == 200:
            d = res.json()
            data = d.get("data", [])
            while d.get("pagination_key"):
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(
                    f"{self.API_URL}/v2/markets/calendar",
                    params=params,
                    headers=self.headers,
                )
                d = res.json()
                data += d.get("data", [])

            df = pd.DataFrame(data)
            if not df.empty:
                df["source"] = "j-quants"
                res = df.to_dict(orient="records")
                return res, df
            else:
                return [], pd.DataFrame()

        logger.error(f"API Error: {res.status_code} - {res.text}")
        return [], pd.DataFrame()


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    カラム名をJ-Quants APIの形式に統一し、型変換を行う

    日次株価のフィールド定義に基づいた型変換:
    - Date: string (YYYY-MM-DD) → datetime
    - Code: string → string
    - 数値フィールド: number → float
      (Open, High, Low, Close, Volume, TurnoverValue,
       UpperLimit, LowerLimit, AdjustmentFactor,
       AdjustmentOpen, AdjustmentHigh, AdjustmentLow,
       AdjustmentClose, AdjustmentVolume)
    """
    # V2 APIのカラム名短縮をV1相当にマッピングして戻す
    v2_column_mapping = {
        "O": "Open",
        "H": "High",
        "L": "Low",
        "C": "Close",
        "Vo": "Volume",
        "Va": "TurnoverValue",
        "AdjO": "AdjustmentOpen",
        "AdjH": "AdjustmentHigh",
        "AdjL": "AdjustmentLow",
        "AdjC": "AdjustmentClose",
        "AdjVo": "AdjustmentVolume",
        "AdjFactor": "AdjustmentFactor",
    }
    df = df.rename(columns=v2_column_mapping)

    # Date列をdatetime型に変換
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])

    # Code列はstring型として保持（明示的に変換）
    if "Code" in df.columns:
        df["Code"] = df["Code"].astype(str)

    # 数値フィールドの定義
    numeric_fields = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "TurnoverValue",
        "UpperLimit",
        "LowerLimit",
        "AdjustmentFactor",
        "AdjustmentOpen",
        "AdjustmentHigh",
        "AdjustmentLow",
        "AdjustmentClose",
        "AdjustmentVolume",
    ]

    # DataFrameに存在する数値フィールドのみ変換
    for field in numeric_fields:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors="coerce")

    # カラムの順序を統一（存在するカラムのみを対象にする）
    column_order = [
        "Code",
        "Open",
        "High",
        "Low",
        "Close",
        "UpperLimit",
        "LowerLimit",
        "Volume",
        "TurnoverValue",
        "AdjustmentFactor",
        "AdjustmentOpen",
        "AdjustmentHigh",
        "AdjustmentLow",
        "AdjustmentClose",
        "AdjustmentVolume",
    ]
    available_columns = [col for col in column_order if col in df.columns]

    # 既存のカラムでcolumn_orderにないものは末尾に追加する
    other_columns = [col for col in df.columns if col not in column_order]

    df = df[available_columns + other_columns].copy()

    # インデックス（日付）をDateカラムに変換
    if "Date" in df.columns:
        df.set_index("Date", drop=False, inplace=True)
        df.index.name = None
        df["Date"] = df.index

    return df
