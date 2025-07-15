from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from abc import ABC, abstractmethod
import time
import json
import hashlib
import os
import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream, HttpSubStream
from airbyte_cdk.models import SyncMode

try:
    from google.cloud import storage
    from google.oauth2 import service_account
except ImportError:
    storage = None
    service_account = None

# 日本標準時
JST = timezone(timedelta(hours=9))


def convert_ecforce_datetime(date_str: Optional[str]) -> Optional[str]:
    """ecforceの日時フォーマットをISO 8601形式に変換
    
    Args:
        date_str: "YYYY/MM/DD HH:mm:ss"形式の日時文字列
        
    Returns:
        ISO 8601形式の文字列、またはNone（入力がNone/空の場合）
    """
    if not date_str:
        return None
    
    try:
        # ecforceフォーマットをパース: "2025/07/09 13:03:03"
        dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")
        # ISO 8601形式で返す: "2025-07-09T13:03:03"
        return dt.isoformat()
    except ValueError:
        # パースに失敗した場合は元の値を返す
        return date_str


def convert_ecforce_date(date_str: Optional[str]) -> Optional[str]:
    """ecforceの日付フォーマットをISO 8601形式に変換
    
    Args:
        date_str: "YYYY/MM/DD"形式の日付文字列
        
    Returns:
        ISO 8601日付形式の文字列、またはNone（入力がNone/空の場合）
    """
    if not date_str:
        return None
    
    try:
        # ecforceフォーマットをパース: "1994/01/01"
        dt = datetime.strptime(date_str, "%Y/%m/%d")
        # ISO 8601日付形式で返す: "1994-01-01"
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        # パースに失敗した場合は元の値を返す
        return date_str


class GCSHelper:
    """GCS操作用のヘルパークラス"""
    
    def __init__(self, bucket_name: str, service_account_key: str, company_name: str):
        """GCSクライアントを初期化 - 必須"""
        self.bucket_name = bucket_name
        self.company_name = company_name
        
        if not storage or not service_account:
            raise ImportError("google-cloud-storage is required. Please install it with: pip install google-cloud-storage")
        
        if not bucket_name or not service_account_key:
            raise ValueError("GCS bucket name and service account key are required")
        
        try:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(service_account_key)
            )
            self.client = storage.Client(credentials=credentials)
            self.bucket = self.client.bucket(bucket_name)
        except json.JSONDecodeError:
            raise ValueError("Invalid service account key JSON")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to GCS: {str(e)}")
    
    def save_response(self, stream_name: str, slice_key: str, data: dict) -> str:
        """APIレスポンスをGCSに保存"""
        # ストリーム、会社名、スライスに基づいて一意のファイル名を作成
        filename = f"ecforce/{self.company_name}/{stream_name}/{slice_key}.json"
        blob = self.bucket.blob(filename)
        
        # JSONとしてデータを保存
        blob.upload_from_string(
            json.dumps(data, ensure_ascii=False),
            content_type="application/json"
        )
        
        return filename
    
    def load_response(self, stream_name: str, slice_key: str) -> Optional[dict]:
        """GCSからAPIレスポンスを読み込み"""
        filename = f"ecforce/{self.company_name}/{stream_name}/{slice_key}.json"
        blob = self.bucket.blob(filename)
        
        if blob.exists():
            data = blob.download_as_text()
            return json.loads(data)
        
        return None


class EcforceStream(HttpStream):
    """ecforce API用のベースストリームクラス"""
    
    primary_key = "id"
    page_size = 100  # ecforce APIの最大ページサイズ
    cursor_field = "updated_at"  # 増分同期に使用するフィールド
    
    @property
    def max_retries(self) -> int:
        """レート制限対応のためのリトライ回数を設定"""
        return 3
    
    @property
    def retry_factor(self) -> float:
        """指数バックオフの係数"""
        return 2.0
    
    def should_retry(self, response: requests.Response) -> bool:
        """レート制限(429)とサーバーエラー(5xx)の場合にリトライ"""
        return response.status_code == 429 or 500 <= response.status_code < 600
    
    def backoff_time(self, response: requests.Response) -> Optional[float]:
        """レスポンスに基づいてバックオフ時間を返す"""
        if response.status_code == 429:
            # Retry-Afterヘッダーを確認
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
            # レート制限のデフォルトは60秒
            return 60.0
        # その他のリトライ可能なエラーのデフォルト指数バックオフ
        return None
    
    @property
    def supports_incremental(self) -> bool:
        """このストリームは増分同期をサポート"""
        return True
    
    def __init__(self, domain: str, start_date: Optional[str] = None, end_date: Optional[str] = None, api_token: str = None, gcs_helper: Optional[GCSHelper] = None, request_interval: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self.domain = domain
        # start_dateが指定されていない場合は2年前を使用
        self.start_date = start_date or (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        # end_dateが指定されていない場合は日本時間の昨日を使用
        self.end_date = end_date or (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
        self._base_url = f"https://{domain}/api/v2/admin"
        self.api_token = api_token
        self.gcs_helper = gcs_helper
        self.request_interval = request_interval
    
    @property
    def url_base(self) -> str:
        return self._base_url
    
    def request_headers(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> Mapping[str, Any]:
        """認証情報を含むリクエストヘッダーを返す"""
        headers = super().request_headers(stream_state, stream_slice, next_page_token)
        headers["Authorization"] = f"Token token={self.api_token}"
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        return headers
    
    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """レスポンスから次ページのトークンを取得"""
        json_response = response.json()
        meta = json_response.get("meta", {})
        current_page = meta.get("page", 1)
        total_pages = meta.get("total_pages", 1)
        
        if current_page < total_pages:
            return {"page": current_page + 1}
        return None
    
    def request_params(
        self, 
        stream_state: Mapping[str, Any], 
        stream_slice: Mapping[str, Any] = None, 
        next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        """リクエストパラメータを構築"""
        params = {
            "per": self.page_size,
            "page": 1,
            "sort": "updated_at,id",
            "lighter": 0,
        }
        
        # stream_sliceが利用可能な場合は日付範囲に使用（月次スライス用）
        if stream_slice and "start_date" in stream_slice and "end_date" in stream_slice:
            params["q[updated_at_gteq]"] = f"{stream_slice['start_date']} 00:00:00"
            params["q[updated_at_lt]"] = f"{stream_slice['end_date']} 23:59:59"
        else:
            # 元の日付範囲にフォールバック
            params["q[updated_at_gteq]"] = f"{self.start_date} 00:00:00"
            params["q[updated_at_lt]"] = f"{self.end_date} 23:59:59"
        
        # ページネーションを追加
        if next_page_token:
            params["page"] = next_page_token["page"]
        
        return params
    
    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]) -> MutableMapping[str, Any]:
        """最新レコードのカーソルフィールド値でstateを更新 - 月次更新"""
        latest_timestamp = latest_record.get(self.cursor_field)
        if not latest_timestamp:
            return current_stream_state
            
        # 最新のタイムスタンプをパース
        if "T" in latest_timestamp:
            latest_date = datetime.fromisoformat(latest_timestamp.replace("Z", "+00:00")).date()
        else:
            latest_date = datetime.strptime(latest_timestamp, "%Y-%m-%d").date()
        
        # 現在のstateの日付を取得
        current_timestamp = current_stream_state.get(self.cursor_field)
        if current_timestamp:
            if "T" in current_timestamp:
                current_date = datetime.fromisoformat(current_timestamp.replace("Z", "+00:00")).date()
            else:
                current_date = datetime.strptime(current_timestamp, "%Y-%m-%d").date()
        else:
            current_date = None
        
        # 最新日付から当月末を計算
        if latest_date.month == 12:
            next_month_start = latest_date.replace(year=latest_date.year + 1, month=1, day=1)
        else:
            next_month_start = latest_date.replace(month=latest_date.month + 1, day=1)
        end_of_month = next_month_start - timedelta(days=1)
        
        # end_date（日本時間の昨日）を最大日付として使用
        end_date_parsed = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        state_date = min(end_of_month, end_date_parsed)
        
        # 新しい月に移ったか、end_dateに達した場合のみstateを更新
        if not current_date or state_date > current_date:
            return {self.cursor_field: state_date.strftime("%Y-%m-%d")}
        
        return current_stream_state
    
    def stream_slices(
        self, 
        sync_mode, 
        cursor_field: List[str] = None, 
        stream_state: Mapping[str, Any] = None
    ) -> Iterable[Optional[Mapping[str, Any]]]:
        """増分同期用の月次スライスを生成"""
        # 開始日を決定
        start_date_str = self.start_date
        if stream_state and self.cursor_field in stream_state:
            # 最後に同期した日付から再開
            last_timestamp = stream_state[self.cursor_field]
            if "T" in last_timestamp:
                # タイムスタンプから日付を抽出し、1日追加して再処理を回避
                last_date = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00")).date()
                start_date_str = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                # 日付形式の場合も1日追加して再処理を回避
                last_date = datetime.strptime(last_timestamp, "%Y-%m-%d").date()
                start_date_str = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # 日付をパース
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        
        # 月次スライスを生成
        current_date = start_date
        first_slice = True
        while current_date <= end_date:
            # 2つ目以降のスライスの前にrequest_interval秒スリープ
            if not first_slice:
                time.sleep(self.request_interval)
            else:
                first_slice = False
            
            # 月の開始日と終了日を計算
            month_start = current_date.replace(day=1)
            # 次月の1日から1日引いて月末を取得
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
            
            # スライスの開始日と終了日を決定
            slice_start = max(current_date, month_start)
            slice_end = min(month_end, end_date)
            
            yield {
                "start_date": slice_start.strftime("%Y-%m-%d"),
                "end_date": slice_end.strftime("%Y-%m-%d")
            }
            
            # 次の月へ移動
            if month_end.month == 12:
                current_date = month_end.replace(year=month_end.year + 1, month=1, day=1)
            else:
                current_date = month_end.replace(month=month_end.month + 1, day=1)


class CustomersStream(EcforceStream):
    """ecforce顧客用の親ストリーム"""
    
    name = "customers"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 子ストリーム用に生レスポンスを保存
        self._current_response_data = None
    
    def path(self, **kwargs) -> str:
        return "admin/customers.json"
    
    def request_params(
        self, 
        stream_state: Mapping[str, Any], 
        stream_slice: Mapping[str, Any] = None, 
        next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        """ノートを含むリクエストパラメータを構築"""
        params = super().request_params(stream_state, stream_slice, next_page_token)
        params["include"] = "notes"
        return params
    
    def parse_response(self, response: requests.Response, stream_slice: Mapping[str, Any] = None, **kwargs) -> Iterable[Mapping]:
        """APIレスポンスをパース - 顧客データのみ"""
        # パース前にレート制限を確認
        if response.status_code == 429:
            self.logger.warning(f"Rate limit hit for {self.name} stream. Status: {response.status_code}")
            # リトライ機構に処理を任せる
            response.raise_for_status()
        
        json_response = response.json()
        
        # 子ストリーム用にレスポンスデータを保存
        self._current_response_data = json_response
        
        # ヘルパーが利用可能な場合はGCSに保存
        if self.gcs_helper and stream_slice:
            # レスポンスメタデータからページ番号を抽出
            page = json_response.get("meta", {}).get("page", 1)
            slice_key = f"{stream_slice['start_date']}_{stream_slice['end_date']}_page{page}"
            
            # レスポンス全体（dataとincluded）を保存 - 必須
            self.gcs_helper.save_response(self.name, slice_key, json_response)
            self.logger.info(f"Saved {len(json_response.get('data', []))} records to GCS for slice {slice_key}")
        
        # メインの顧客データを処理
        for record in json_response.get("data", []):
            attributes = record.get("attributes", {})
            
            # 日時フィールドをISO 8601形式に変換
            if "created_at" in attributes:
                attributes["created_at"] = convert_ecforce_datetime(attributes["created_at"])
            if "updated_at" in attributes:
                attributes["updated_at"] = convert_ecforce_datetime(attributes["updated_at"])
            if "deleted_at" in attributes:
                attributes["deleted_at"] = convert_ecforce_datetime(attributes["deleted_at"])
            if "first_order_completed_at" in attributes:
                attributes["first_order_completed_at"] = convert_ecforce_datetime(attributes["first_order_completed_at"])
            if "last_order_completed_at" in attributes:
                attributes["last_order_completed_at"] = convert_ecforce_datetime(attributes["last_order_completed_at"])
            if "point_expired_at" in attributes:
                attributes["point_expired_at"] = convert_ecforce_datetime(attributes["point_expired_at"])
            
            # 日付フィールドをISO 8601日付形式に変換
            if "birth" in attributes:
                attributes["birth"] = convert_ecforce_date(attributes["birth"])
            
            # ターゲットスキーマにないフィールドを削除
            if "type" in attributes:
                del attributes["type"]
            if "accepts_marketing_updated_at" in attributes:
                del attributes["accepts_marketing_updated_at"]
            if "is_auto_generated_email" in attributes:
                del attributes["is_auto_generated_email"]
            
            # 必要に応じてフィールド名をマッピング
            if "email" in attributes:
                # emailフィールドは既に正しい名前
                pass
            if "name" in attributes:
                del attributes["name"]
            if "name_kana" in attributes:
                del attributes["name_kana"]
            if "tel" in attributes:
                del attributes["tel"]
            if "mobile" in attributes:
                del attributes["mobile"]
            if "mobile_email" in attributes:
                del attributes["mobile_email"]
            if "birthday" in attributes:
                del attributes["birthday"]
            if "postal_code" in attributes:
                del attributes["postal_code"]
            if "prefecture" in attributes:
                del attributes["prefecture"]
            if "city" in attributes:
                del attributes["city"]
            if "street" in attributes:
                del attributes["street"]
            if "building" in attributes:
                del attributes["building"]
            if "company_name" in attributes:
                del attributes["company_name"]
            if "department" in attributes:
                del attributes["department"]
            if "customer_code" in attributes:
                del attributes["customer_code"]
            if "customer_status" in attributes:
                del attributes["customer_status"]
            
            customer_data = {
                "id": int(record.get("id")),
                **attributes
            }
            yield customer_data
        
        # ページネーション時のレート制限対策（最後のページ以外）
        if self.next_page_token(response) is not None:
            time.sleep(self.request_interval)
    
    def get_json_schema(self) -> Mapping[str, Any]:
        """Return schema for customers stream"""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "顧客ID"
                },
                "authentication_token": {
                    "type": ["string", "null"],
                    "description": "認証トークン"
                },
                "number": {
                    "type": ["string", "null"],
                    "description": "顧客番号"
                },
                "state": {
                    "type": ["string", "null"],
                    "description": "会員ステータス"
                },
                "human_state_name": {
                    "type": ["string", "null"],
                    "description": "会員ステータス（日本語）"
                },
                "customer_rank_name": {
                    "type": ["string", "null"],
                    "description": "会員ランク名"
                },
                "sex_id": {
                    "type": ["integer", "null"],
                    "description": "性別ID"
                },
                "sex": {
                    "type": ["string", "null"],
                    "description": "性別"
                },
                "job": {
                    "type": ["string", "null"],
                    "description": "職業"
                },
                "birth": {
                    "type": ["string", "null"],
                    "format": "date",
                    "description": "生年月日"
                },
                "buy_times": {
                    "type": ["integer", "null"],
                    "description": "顧客購入回数"
                },
                "buy_total": {
                    "type": ["integer", "null"],
                    "description": "購入総額"
                },
                "first_order_completed_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "初回受注日時"
                },
                "last_order_completed_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "最終受注日時"
                },
                "point": {
                    "type": ["integer", "null"],
                    "description": "合計ポイント"
                },
                "point_expired_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "ポイント有効期限"
                },
                "customer_type_name": {
                    "type": ["string", "null"],
                    "description": "顧客タイプ名"
                },
                "optin": {
                    "type": ["boolean", "null"],
                    "description": "メールマガジン受け取り"
                },
                "line_id": {
                    "type": ["string", "null"],
                    "description": "LINE ID"
                },
                "tenant_id": {
                    "type": ["integer", "null"],
                    "description": "テナント ID"
                },
                "mail_delivery_stop": {
                    "type": ["boolean", "null"],
                    "description": "メール送信しない"
                },
                "np_royal_customer": {
                    "type": ["boolean", "null"],
                    "description": "NP後払いリアルタイムロイヤルカスタマー"
                },
                "blacklist": {
                    "type": ["boolean", "null"],
                    "description": "ブラックリスト"
                },
                "blacklist_reasons": {
                    "type": ["string", "null"],
                    "description": "ブラックリスト理由"
                },
                "labels": {
                    "type": ["string", "null"],
                    "description": "顧客ラベル"
                },
                "coupon_codes": {
                    "type": ["string", "null"],
                    "description": "クーポンコード"
                },
                "link_number": {
                    "type": ["string", "null"],
                    "description": "連携用顧客番号"
                },
                "created_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "入会日"
                },
                "updated_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "更新日"
                },
                "deleted_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "退会日"
                }
            }
        }


class CustomerNotesStream(HttpSubStream):
    """Child stream for customer notes - depends on CustomersStream"""
    
    name = "customer_notes"
    primary_key = "id"
    cursor_field = "updated_at"
    
    def __init__(self, parent: CustomersStream, **kwargs):
        super().__init__(parent=parent, **kwargs)
    
    @property
    def supports_incremental(self) -> bool:
        """このストリームは増分同期をサポート"""
        return True
    
    def path(self, **kwargs) -> str:
        """Not used - we get data from parent stream"""
        return "not_used"
    
    @property
    def url_base(self) -> str:
        """Not used - we get data from parent stream"""
        return self.parent.url_base
    
    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """Not used - we get data from parent stream"""
        return None
    
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        """Not used - we get data from parent stream"""
        return []
    
    def stream_slices(self, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        """Return parent stream slices to process"""
        # 親ストリームのスライスを取得
        parent_stream_slices = self.parent.stream_slices(**kwargs)
        
        for parent_slice in parent_stream_slices:
            # 各親スライスを返す
            yield parent_slice
    
    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: List[str] = None,
        stream_slice: Mapping[str, Any] = None,
        stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        """Extract notes from GCS stored data"""
        if not stream_slice or not self.parent.gcs_helper:
            return
            
        # このスライスのすべてのページをGCSから取得
        page = 1
        while True:
            slice_key = f"{stream_slice['start_date']}_{stream_slice['end_date']}_page{page}"
            data = self.parent.gcs_helper.load_response(self.parent.name, slice_key)
            
            if not data:
                # これ以上ページがない
                break
                
            # 読み込んだデータからノートをパース
            yield from self._parse_notes_from_response(data)
            
            page += 1
    
    def _parse_notes_from_response(self, json_response: dict) -> Iterable[Mapping]:
        
        # included dataのインデックスマップを作成
        included_map = {}
        if "included" in json_response:
            for item in json_response["included"]:
                if item["type"] == "note":
                    included_map[item["id"]] = item
        
        # 顧客データを処理してノートと顧客の関係を抽出
        for record in json_response.get("data", []):
            customer_id = record.get("id")
            relationships = record.get("relationships", {})
            notes_data = relationships.get("notes", {}).get("data", [])
            
            for note_ref in notes_data:
                if note_ref["id"] in included_map:
                    note = included_map[note_ref["id"]]
                    note_attributes = note.get("attributes", {})
                    
                    # 日時フィールドをISO 8601形式に変換
                    if "created_at" in note_attributes:
                        note_attributes["created_at"] = convert_ecforce_datetime(note_attributes["created_at"])
                    if "updated_at" in note_attributes:
                        note_attributes["updated_at"] = convert_ecforce_datetime(note_attributes["updated_at"])
                    if "operated_at" in note_attributes:
                        note_attributes["operated_at"] = convert_ecforce_datetime(note_attributes["operated_at"])
                    
                    yield {
                        "id": int(note["id"]),
                        "customer_id": int(customer_id),
                        **note_attributes
                    }
    
    def get_json_schema(self) -> Mapping[str, Any]:
        """Return schema for customer notes stream"""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "メモID"
                },
                "customer_id": {
                    "type": ["integer", "null"],
                    "description": "顧客ID"
                },
                "content": {
                    "type": ["string", "null"],
                    "description": "メモ"
                },
                "operated_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "受付日"
                },
                "created_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "作成日"
                },
                "updated_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "更新日"
                },
            }
        }


class SourceEcforce(AbstractSource):
    """Source implementation for ecforce with separate notes stream"""
    
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """Check connection to ecforce API"""
        try:
            # customersエンドポイントでテスト
            stream = CustomersStream(
                domain=config["domain"],
                start_date=config.get("start_date"),  # オプション
                api_token=config["api_token"],
                request_interval=config.get("request_interval", 1.0)
            )
            
            # 1レコード読み込みを試行
            records = stream.read_records(sync_mode=SyncMode.full_refresh)
            next(records)
            
            return True, None
        except StopIteration:
            # レコードがなくても接続は成功
            return True, None
        except Exception as e:
            return False, f"Unable to connect to ecforce API: {str(e)}"
    
    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """Return list of streams"""
        # すべてのストリームで共通のstart_dateとend_dateを使用
        start_date = config.get("start_date")
        end_date = config.get("end_date")
        
        # 設定されていればGCSヘルパーを初期化
        gcs_helper = None
        if config.get("gcs_bucket") and config.get("gcs_service_account_key"):
            gcs_helper = GCSHelper(
                bucket_name=config["gcs_bucket"],
                service_account_key=config["gcs_service_account_key"],
                company_name=config["company_name"]
            )
        
        # request_intervalを取得（デフォルトは1秒）
        request_interval = config.get("request_interval", 1.0)
        
        # 親ストリームを作成
        customers_stream = CustomersStream(
            domain=config["domain"],
            start_date=start_date,
            end_date=end_date,
            api_token=config["api_token"],
            gcs_helper=gcs_helper,
            request_interval=request_interval
        )
        
        streams = [customers_stream]
        
        # リクエストされた場合は顧客ノートストリームを追加（customersストリームの子として）
        if config.get("include_notes", False):
            streams.append(
                CustomerNotesStream(
                    parent=customers_stream
                )
            )
        
        return streams
