from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from datetime import datetime
from urllib.parse import urljoin
from abc import ABC, abstractmethod
import time

import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.models import SyncMode


def convert_ecforce_datetime(date_str: Optional[str]) -> Optional[str]:
    """Convert ecforce datetime format to ISO 8601 format
    
    Args:
        date_str: Date string in format "YYYY/MM/DD HH:mm:ss"
        
    Returns:
        ISO 8601 formatted string or None if input is None/empty
    """
    if not date_str:
        return None
    
    try:
        # Parse ecforce format: "2025/07/09 13:03:03"
        dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")
        # Return ISO 8601 format: "2025-07-09T13:03:03"
        return dt.isoformat()
    except ValueError:
        # Return original if parse fails
        return date_str


def convert_ecforce_date(date_str: Optional[str]) -> Optional[str]:
    """Convert ecforce date format to ISO 8601 date format
    
    Args:
        date_str: Date string in format "YYYY/MM/DD"
        
    Returns:
        ISO 8601 date formatted string or None if input is None/empty
    """
    if not date_str:
        return None
    
    try:
        # Parse ecforce format: "1994/01/01"
        dt = datetime.strptime(date_str, "%Y/%m/%d")
        # Return ISO 8601 date format: "1994-01-01"
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        # Return original if parse fails
        return date_str


class EcforceStream(HttpStream):
    """Base stream class for ecforce API"""
    
    primary_key = "id"
    page_size = 100  # ecforce API max page size
    
    @property
    def max_retries(self) -> int:
        """No retries - fail immediately on error"""
        return 0
    
    def __init__(self, domain: str, start_date: str, end_date: Optional[str] = None, api_token: str = None, **kwargs):
        super().__init__(**kwargs)
        self.domain = domain
        self.start_date = start_date
        # If end_date is not provided, use today's date
        self.end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        self._base_url = f"https://{domain}/api/v2/admin"
        self.api_token = api_token
    
    @property
    def url_base(self) -> str:
        return self._base_url
    
    def request_headers(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> Mapping[str, Any]:
        """Return request headers with authentication"""
        headers = super().request_headers(stream_state, stream_slice, next_page_token)
        headers["Authorization"] = f"Token token={self.api_token}"
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        return headers
    
    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """Get next page token from response"""
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
        """Build request parameters"""
        params = {
            "per": self.page_size,
            "page": 1,
            "sort": "updated_at,id",
            "lighter": 0,
        }
        
        # Add date filters using q parameter format
        # Always use 00:00:00 for start and 23:59:59 for end
        params["q[updated_at_gteq]"] = f"{self.start_date} 00:00:00"
        params["q[updated_at_lt]"] = f"{self.end_date} 23:59:59"
        
        # Add pagination
        if next_page_token:
            params["page"] = next_page_token["page"]
        
        return params
    
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        """Parse API response"""
        json_response = response.json()
        
        # Extract main data
        for record in json_response.get("data", []):
            # Flatten attributes into the main record
            attributes = record.get("attributes", {})
            yield {
                "id": record.get("id"),
                "type": record.get("type"),
                **attributes
            }
        
        # Wait 1 second after each successful request (except for the last page)
        if self.next_page_token(response) is not None:
            time.sleep(1.0)


class CustomersWithNotesStream(EcforceStream):
    """Base stream that fetches customers with notes included"""
    
    def path(self, **kwargs) -> str:
        return "admin/customers.json"
    
    def request_params(
        self, 
        stream_state: Mapping[str, Any], 
        stream_slice: Mapping[str, Any] = None, 
        next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        """Build request parameters with notes included"""
        params = super().request_params(stream_state, stream_slice, next_page_token)
        params["include"] = "notes"
        return params
    
    @abstractmethod
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        """Must be implemented by subclasses"""
        pass


class CustomersStream(CustomersWithNotesStream):
    """Stream for ecforce customers (without notes in the data)"""
    
    name = "customers"
    
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        """Parse API response - customers data only"""
        json_response = response.json()
        
        # Process main customer data
        for record in json_response.get("data", []):
            attributes = record.get("attributes", {})
            
            # Convert datetime fields to ISO 8601 format
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
            
            # Convert date fields to ISO 8601 date format
            if "birth" in attributes:
                attributes["birth"] = convert_ecforce_date(attributes["birth"])
            
            # Remove fields not in the target schema
            if "type" in attributes:
                del attributes["type"]
            if "accepts_marketing_updated_at" in attributes:
                del attributes["accepts_marketing_updated_at"]
            if "is_auto_generated_email" in attributes:
                del attributes["is_auto_generated_email"]
            
            # Map some field names if needed
            if "email" in attributes:
                # email field is already named correctly
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


class CustomerNotesStream(CustomersWithNotesStream):
    """Stream for customer notes extracted from the same API call"""
    
    name = "customer_notes"
    primary_key = "id"
    
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        """Parse API response - extract notes from included data"""
        json_response = response.json()
        
        # Create index map for included data
        included_map = {}
        if "included" in json_response:
            for item in json_response["included"]:
                if item["type"] == "note":
                    included_map[item["id"]] = item
        
        # Process customer data to extract notes with customer relationship
        for record in json_response.get("data", []):
            customer_id = record.get("id")
            relationships = record.get("relationships", {})
            notes_data = relationships.get("notes", {}).get("data", [])
            
            for note_ref in notes_data:
                if note_ref["id"] in included_map:
                    note = included_map[note_ref["id"]]
                    note_attributes = note.get("attributes", {})
                    
                    # Convert datetime fields to ISO 8601 format
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
            # Test with customers endpoint
            stream = CustomersStream(
                domain=config["domain"],
                start_date=config["start_date"],
                end_date=config.get("end_date"),
                api_token=config["api_token"]
            )
            
            # Try to read one record
            records = stream.read_records(sync_mode=SyncMode.full_refresh)
            next(records)
            
            return True, None
        except StopIteration:
            # No records is OK, connection works
            return True, None
        except Exception as e:
            return False, f"Unable to connect to ecforce API: {str(e)}"
    
    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """Return list of streams"""
        streams = [
            CustomersStream(
                domain=config["domain"],
                start_date=config["start_date"],
                end_date=config.get("end_date"),
                api_token=config["api_token"]
            )
        ]
        
        # Add customer notes stream if requested
        if config.get("include_notes", False):
            streams.append(
                CustomerNotesStream(
                    domain=config["domain"],
                    start_date=config["start_date"],
                    end_date=config.get("end_date"),
                    api_token=config["api_token"]
                )
            )
        
        return streams
