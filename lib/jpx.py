import requests
import pandas as pd
from io import BytesIO
from typing import Tuple, List
from datetime import datetime
import logging
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class JPX:
    """
    JPX決算発表予定日Excelファイル取得クラス
    """
    
    BASE_URL = "https://www.jpx.co.jp"
    ANNOUNCEMENT_PAGE_URL = "https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def _scrape_excel_urls(self) -> List[str]:
        """
        JPXのウェブページをスクレイピングしてExcelファイルのURLを取得
        
        Returns:
            ExcelファイルのURLのリスト
        """
        try:
            response = self.session.get(self.ANNOUNCEMENT_PAGE_URL)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            excel_urls = []
            
            # Excelファイルへのリンクを検索（.xlsx拡張子を持つリンク）
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if href and href.endswith('.xlsx'):
                    # 相対パスの場合は絶対URLに変換
                    if href.startswith('/'):
                        full_url = self.BASE_URL + href
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = self.BASE_URL + '/' + href
                    
                    excel_urls.append(full_url)
            
            # 重複を除去
            excel_urls = list(set(excel_urls))
            
            logger.info(f"Excelファイルを{len(excel_urls)}件発見しました")
            return excel_urls
            
        except Exception as e:
            logger.error(f"ExcelファイルURLの取得に失敗しました: {e}")
            return []
    
    def _download_excel(self, url: str) -> pd.DataFrame:
        """
        ExcelファイルをダウンロードしてDataFrameとして読み込む
        
        Args:
            url: ExcelファイルのURL
            
        Returns:
            読み込んだDataFrame（失敗時は空のDataFrame）
        """
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            # Excelファイルを読み込む（ヘッダー行は4行目）
            df = pd.read_excel(BytesIO(response.content), header=4)
            
            return df
            
        except Exception as e:
            logger.error(f"Excelファイルのダウンロード/読み込みに失敗しました ({url}): {e}")
            return pd.DataFrame()
    
    def _parse_excel(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        ExcelファイルのDataFrameをパースして、J-Quants APIと同じ形式に変換
        
        Args:
            df: 読み込んだExcelファイルのDataFrame
            
        Returns:
            パース済みのDataFrame
        """
        if df.empty:
            return df
        
        try:
            # 列名を確認（実際の列名は日本語と英語が混在している可能性がある）
            # 列0: 決算発表予定日
            # 列1: コード
            # 列2: 会社名
            # 列3: 決算期末
            # 列4: 業種名
            # 列5: 種別（Fiscal Year/Quarter）
            # 列6: 市場区分
            
            # 列構造:
            # 列0: 決算発表予定日
            # 列1: コード
            # 列2: 会社名（日本語）
            # 列3: Issue Name（会社名英語）
            # 列4: 決算期末
            # 列5: 業種名（日本語）
            # 列6: Industry（業種名英語）
            # 列7: 種別（日本語、例：第２四半期）
            # 列8: Fiscal Year/Quarter（英語）
            # 列9: 市場区分（日本語）
            # 列10: Market Segment（英語）
            
            parsed_data = []
            
            for idx, row in df.iterrows():
                # 決算発表予定日を取得（列0）
                announcement_date = row.iloc[0]
                
                # 日付が有効でない場合はスキップ
                if pd.isna(announcement_date) or not isinstance(announcement_date, (datetime, pd.Timestamp)):
                    continue
                
                # コードを取得（列1）
                code = row.iloc[1]
                if pd.isna(code):
                    continue
                
                # コードを文字列に変換（4桁の0埋め）
                code_str = str(int(code)).zfill(4) if isinstance(code, (int, float)) else str(code).strip()
                
                # 会社名を取得（列2: 日本語）
                company_name = row.iloc[2] if len(row) > 2 else ""
                company_name = str(company_name).strip() if not pd.isna(company_name) else ""
                
                # 決算期末を取得（列4）
                fiscal_year_end = row.iloc[4] if len(row) > 4 else None
                
                # 種別を取得（列7: 日本語、例：第２四半期）
                fiscal_quarter = row.iloc[7] if len(row) > 7 else ""
                fiscal_quarter = str(fiscal_quarter).strip() if not pd.isna(fiscal_quarter) else ""
                
                # 日付を文字列形式に変換（YYYY-MM-DD）
                date_str = announcement_date.strftime("%Y-%m-%d") if isinstance(announcement_date, (datetime, pd.Timestamp)) else str(announcement_date)
                
                # 決算期末を文字列形式に変換
                fiscal_year_end_str = ""
                if not pd.isna(fiscal_year_end):
                    if isinstance(fiscal_year_end, (datetime, pd.Timestamp)):
                        fiscal_year_end_str = fiscal_year_end.strftime("%Y-%m-%d")
                    else:
                        fiscal_year_end_str = str(fiscal_year_end)
                
                # 決算年度を取得（決算期末の年から）
                fiscal_year = ""
                if fiscal_year_end_str:
                    try:
                        if isinstance(fiscal_year_end, (datetime, pd.Timestamp)):
                            fiscal_year = str(fiscal_year_end.year)
                        else:
                            # 文字列から年を抽出
                            date_parts = str(fiscal_year_end).split('-')
                            if len(date_parts) > 0:
                                fiscal_year = date_parts[0]
                    except:
                        pass
                
                parsed_data.append({
                    'Code': code_str,
                    'CompanyName': company_name,
                    'Date': date_str,
                    'AnnouncementDate': date_str,
                    'FiscalYearEnd': fiscal_year_end_str,
                    'FiscalQuarter': fiscal_quarter,
                    'FiscalYear': fiscal_year,
                    'source': 'jpx-excel'
                })
            
            result_df = pd.DataFrame(parsed_data)
            
            if not result_df.empty:
                logger.info(f"{len(result_df)}件の決算発表予定日データをパースしました")
            
            return result_df
            
        except Exception as e:
            logger.error(f"Excelファイルのパースに失敗しました: {e}")
            return pd.DataFrame()
    
    def get_fins_announcement(self) -> Tuple[List[dict], pd.DataFrame]:
        """
        決算発表予定日を取得（J-Quants APIと同じ形式で返す）
        
        Returns:
            (list, pd.DataFrame) のタプル
        """
        # ExcelファイルのURLを取得
        excel_urls = self._scrape_excel_urls()
        
        if not excel_urls:
            logger.warning("ExcelファイルのURLが見つかりませんでした")
            return [], pd.DataFrame()
        
        # すべてのExcelファイルをダウンロードしてパース
        all_dataframes = []
        
        for url in excel_urls:
            logger.info(f"Excelファイルを処理中: {url}")
            df = self._download_excel(url)
            if not df.empty:
                parsed_df = self._parse_excel(df)
                if not parsed_df.empty:
                    all_dataframes.append(parsed_df)
        
        # すべてのDataFrameをマージ
        if all_dataframes:
            merged_df = pd.concat(all_dataframes, ignore_index=True)
            # 重複を除去（CodeとDateの組み合わせで）
            merged_df = merged_df.drop_duplicates(subset=['Code', 'Date'], keep='first')
            
            # リスト形式に変換
            result_list = merged_df.to_dict(orient='records')
            
            logger.info(f"合計{len(result_list)}件の決算発表予定日データを取得しました")
            
            return result_list, merged_df
        else:
            logger.warning("有効なデータが取得できませんでした")
            return [], pd.DataFrame()

