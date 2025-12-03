import json
from typing import Tuple
from requests import Response
import requests
import os
from datetime import datetime, timedelta
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
        if hasattr(self, '_initialized'):
            return
            
        self.API_URL = "https://api.jquants.com"
        self.refresh_token = ""
        self.id_token = ""
        self.token_expires_at = None
        self.headers = {}  # 初期化を確実にする
        self._initialized = True
        self.isEnable = self._set_token()
        if self.isEnable:
            self.headers = {'Authorization': 'Bearer {}'.format(self.id_token)}


    def _set_token(self) -> bool:
        """
        リフレッシュトークン及びidTokenを取得
        
        正しく設定ファイルが作成されていれば、本コードを実行することで、idTokenを取得することができます。
        「APIを使用する準備が完了しました。」と出力されれば、J-Quants APIをコールすることができるようになります！
        """
        USER_DATA = {
            "mailaddress": os.getenv('JQuants_EMAIL_ADDRESS'),
            "password": os.getenv('JQuants_PASSWORD'),
        }
        # 環境変数が設定されていない場合はAPI呼び出しを行わない
        if not USER_DATA["mailaddress"] or not USER_DATA["password"]:
            logger.warning("J-Quantsの認証情報が設定されていません。")
            return False
        # refresh token取得
        try:
            res = requests.post(f"{self.API_URL}/v1/token/auth_user", data=json.dumps(USER_DATA))
            self.refresh_token = res.json()['refreshToken']
        except:
            logger.error("RefreshTokenの取得に失敗しました。")
        else:
            # id token取得
            try:
                res = requests.post(f"{self.API_URL}/v1/token/auth_refresh?refreshtoken={self.refresh_token}")
                self.id_token = res.json()['idToken']
                # トークンの有効期限を設定（24時間後）
                self.token_expires_at = datetime.now() + timedelta(hours=24)
            except:
                logger.error("idTokenの取得に失敗しました。")
            else:
                logger.info("API使用の準備が完了しました。")
                return True
        return False

    def _refresh_token_if_needed(self) -> bool:
        """
        トークンが期限切れの場合はリフレッシュする
        """
        if self.token_expires_at:
            # token_expires_atがfloatの場合はdatetimeに変換
            if isinstance(self.token_expires_at, (int, float)):
                self.token_expires_at = datetime.fromtimestamp(self.token_expires_at)
            if datetime.now() >= self.token_expires_at:
                logger.info("トークンの期限が切れているため、リフレッシュします。")
                try:
                    res = requests.post(f"{self.API_URL}/v1/token/auth_refresh?refreshtoken={self.refresh_token}")
                    self.id_token = res.json()['idToken']
                    self.token_expires_at = datetime.now() + timedelta(hours=24)
                    self.headers = {'Authorization': 'Bearer {}'.format(self.id_token)}
                    logger.info("トークンのリフレッシュが完了しました。")
                    return True
                except Exception as e:
                    logger.error(f"トークンのリフレッシュに失敗しました: {e}")
                    return False
        return True


    def get_listed_info(self, code = "", date = "") -> Tuple[list, pd.DataFrame]:
        """
        上場銘柄一覧（/listed/info）

        - 過去時点での銘柄情報、当日の銘柄情報および翌営業日時点の銘柄情報が取得可能です。
        - データの取得では、銘柄コード（code）または日付（date）の指定が可能です。

        （データ更新時刻）
        - 毎営業日の24:00頃
        
        """
        # トークンリフレッシュが必要かチェック
        self._refresh_token_if_needed()
        
        params = {}
        if code != "":
            params["code"] = code
        if date != "":
            params["date"] = date

        res = requests.get(f"{self.API_URL}/v1/listed/info", params=params, headers=self.headers)
        if res.status_code == 200:
            d = res.json()
            data = d["info"]
            while "pagination_key" in d:
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(f"{self.API_URL}/v1/listed/info", params=params, headers=self.headers)
                d = res.json()
                data += d["info"]

            df = pd.DataFrame(data)
            df['source'] = 'j-quants'

            res = df.to_dict(orient='records')

            return res, df

        logger.error(f"API Error: {res.status_code} - {res.json()}")
        return [], pd.DataFrame()

    def get_daily_quotes(self, code: str, from_: datetime = None, to: datetime = None) -> Tuple[list, pd.DataFrame]:
        """
        株価四本値（/prices/daily_quotes）

        - 株価は分割・併合を考慮した調整済み株価（小数点第２位四捨五入）と調整前の株価を取得することができます。
        - データの取得では、銘柄コード（code）または日付（date）の指定が必須となります。

        （データ更新時刻）
        - 毎営業日の17:00頃

        - Premiumプランの方には、日通しに加え、前場(Morning)及び後場(Afternoon)の四本値及び取引高（調整前・後両方）・取引代金が取得可能です。
        - データの取得では、日付（date）を指定して全銘柄取得するモードがあるが、非対応となっています。
        """
        # トークンリフレッシュが必要かチェック
        self._refresh_token_if_needed()

        params = {}
        if code != "":
            params["code"] = code
        if from_ is not None:
            params["from"] = from_.strftime("%Y-%m-%d")
        if to is not None:
            params["to"] = to.strftime("%Y-%m-%d")

        res = requests.get(f"{self.API_URL}/v1/prices/daily_quotes", params=params, headers=self.headers)
        if res.status_code == 200:
            d = res.json()
            data = d["daily_quotes"]
            while "pagination_key" in d:
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(f"{self.API_URL}/v1/prices/daily_quotes", params=params, headers=self.headers)
                d = res.json()
                data += d["daily_quotes"]

            df = pd.DataFrame(data)
            # 型変換（日次株価フィールド定義に基づく）
            df = _normalize_columns(df)
            df['source'] = 'j-quants'

            res = df.to_dict(orient='records')

            return res, df
            
        logger.error(f"API Error: {res.status_code} - {res.json()}")
        return [], pd.DataFrame()


    def get_fins_statements(self, code = "", date = "", from_ = "", to = "") -> Tuple[list, pd.DataFrame]:
        """
        財務情報（/fins/statements）

        - 財務情報APIでは、上場企業がTDnetへ提出する決算短信Summary等を基に作成された、四半期毎の財務情報を取得することができます。
        - データの取得では、銘柄コード（code）または開示日（date）の指定が必須です。

        （データ更新時刻）
        - 速報18:00頃、確報24:30頃
        """
        # トークンリフレッシュが必要かチェック
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

        res = requests.get(f"{self.API_URL}/v1/fins/statements", params=params, headers=self.headers)
        if res.status_code == 200:
            d = res.json()
            data = d["statements"]
            while "pagination_key" in d:
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(f"{self.API_URL}/v1/fins/statements", params=params, headers=self.headers)
                d = res.json()
                data += d["statements"]

            df = pd.DataFrame(data)
            df['source'] = 'j-quants'

            res = df.to_dict(orient='records')

            return res, df

        logger.error(f"API Error: {res.status_code} - {res.json()}")
        return [], pd.DataFrame()

    def get_fins_announcement(self) -> Tuple[list, pd.DataFrame]:
        """
        決算発表予定日（/fins/announcement）

        （データ更新時刻）
        - 不定期（更新がある日は）19:00頃

        - [当該ページ](https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html)で、3月期・９月期決算会社分に更新があった場合のみ19時ごろに更新されます。
        """
        # トークンリフレッシュが必要かチェック
        self._refresh_token_if_needed()
        
        params = {}

        res = requests.get(f"{self.API_URL}/v1/fins/announcement", params=params, headers=self.headers)
        if res.status_code == 200:
            d = res.json()
            data = d["announcement"]
            while "pagination_key" in d:
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(f"{self.API_URL}/v1/fins/announcement", params=params, headers=self.headers)
                d = res.json()
                data += d["announcement"]

            df = pd.DataFrame(data)
            df['source'] = 'j-quants'

            res = df.to_dict(orient='records')

            return res, df

        logger.error(f"API Error: {res.status_code} - {res.json()}")
        return [], pd.DataFrame()

    def get_market_trading_calendar(self, holidaydivision = "", from_ = "", to = "") -> Tuple[list, pd.DataFrame]:
        """
        取引カレンダー（/market/trading_calendar）

        - 東証およびOSEにおける営業日、休業日、ならびにOSEにおける祝日取引の有無の情報を取得できます。
        - データの取得では、休日区分（holidaydivision）または日付（from/to）の指定が可能です。

        （データ更新日）
        - 不定期（原則として、毎年2月頃をめどに翌年1年間の営業日および祝日取引実施日（予定）を更新します。）
        """
        # トークンリフレッシュが必要かチェック
        self._refresh_token_if_needed()

        params = {}
        if holidaydivision != "":
            params["holidaydivision"] = holidaydivision
        if from_ != "":
            params["from"] = from_ 
        if to != "":
            params["to"] = to 

        res = requests.get(f"{self.API_URL}/v1/markets/trading_calendar", params=params, headers=self.headers)
        if res.status_code == 200:
            d = res.json()
            data = d["trading_calendar"]
            while "pagination_key" in d:
                params["pagination_key"] = d["pagination_key"]
                res = requests.get(f"{self.API_URL}/v1/markets/trading_calendar", params=params, headers=self.headers)
                d = res.json()
                data += d["trading_calendar"]

            df = pd.DataFrame(data)
            df['source'] = 'j-quants'

            res = df.to_dict(orient='records')

            return res, df

        logger.error(f"API Error: {res.status_code} - {res.json()}")
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
    # Date列をdatetime型に変換
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])

    # Code列はstring型として保持（明示的に変換）
    if "Code" in df.columns:
        df["Code"] = df["Code"].astype(str)

    # 数値フィールドの定義
    numeric_fields = [
        "Open", "High", "Low", "Close", "Volume", "TurnoverValue",
        "UpperLimit", "LowerLimit", "AdjustmentFactor",
        "AdjustmentOpen", "AdjustmentHigh", "AdjustmentLow",
        "AdjustmentClose", "AdjustmentVolume"
    ]

    # DataFrameに存在する数値フィールドのみ変換
    for field in numeric_fields:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors='coerce')

    # カラムの順序を統一
    column_order = ['Code', 'Open', 'High', 'Low', 'Close',
                    'UpperLimit', 'LowerLimit', 'Volume', 'TurnoverValue',
                    'AdjustmentFactor', 'AdjustmentOpen', 'AdjustmentHigh',
                    'AdjustmentLow', 'AdjustmentClose', 'AdjustmentVolume']
    df = df[column_order].copy()

    # インデックス（日付）をDateカラムに変換
    df['Date'] = df.index

    return df