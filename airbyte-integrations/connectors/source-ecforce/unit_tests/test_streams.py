import pytest
import requests
from unittest.mock import MagicMock, patch
from datetime import datetime
import time

from source_ecforce.source import (
    CustomersStream, 
    CustomerNotesStream,
    convert_ecforce_datetime,
    convert_ecforce_date
)


class TestDateTimeConversion:
    """Test date/time conversion functions"""
    
    def test_convert_ecforce_datetime(self):
        """Test datetime conversion from ecforce format to ISO 8601"""
        assert convert_ecforce_datetime("2025/01/15 10:30:45") == "2025-01-15T10:30:45"
        assert convert_ecforce_datetime("2024/12/31 23:59:59") == "2024-12-31T23:59:59"
        assert convert_ecforce_datetime(None) is None
        assert convert_ecforce_datetime("") is None
        assert convert_ecforce_datetime("invalid") == "invalid"  # Returns original on parse error
    
    def test_convert_ecforce_date(self):
        """Test date conversion from ecforce format to ISO 8601 date"""
        assert convert_ecforce_date("1990/01/01") == "1990-01-01"
        assert convert_ecforce_date("2025/12/31") == "2025-12-31"
        assert convert_ecforce_date(None) is None
        assert convert_ecforce_date("") is None
        assert convert_ecforce_date("invalid") == "invalid"  # Returns original on parse error


class TestEcforceStream:
    """Test base EcforceStream functionality through concrete implementations"""
    
    def test_url_base(self, config):
        """Test URL base construction"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            end_date=config["end_date"],
            api_token=config["api_token"]
        )
        
        assert stream.url_base == f"https://{config['domain']}/api/v2/admin"
    
    def test_request_headers(self, config):
        """Test request headers include proper authentication"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        headers = stream.request_headers()
        
        assert headers["Authorization"] == f"Token token={config['api_token']}"
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"
    
    def test_request_params(self, config):
        """Test request parameters include proper filters"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date="2025-01-01",
            end_date="2025-01-31",
            api_token=config["api_token"]
        )
        
        params = stream.request_params(stream_state={})
        
        assert params["per"] == 100
        assert params["page"] == 1
        assert params["sort"] == "updated_at,id"
        assert params["lighter"] == 0
        assert params["q[updated_at_gteq]"] == "2025-01-01 00:00:00"
        assert params["q[updated_at_lt]"] == "2025-01-31 23:59:59"
    
    def test_request_params_with_pagination(self, config):
        """Test request parameters with pagination token"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date="2025-01-01",
            api_token=config["api_token"]
        )
        
        params = stream.request_params(
            stream_state={},
            next_page_token={"page": 3}
        )
        
        assert params["page"] == 3
    
    def test_next_page_token(self, config, customers_response):
        """Test next page token extraction"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        # Mock response with multiple pages
        response = MagicMock()
        response.json.return_value = {
            "meta": {
                "page": 1,
                "total_pages": 3
            }
        }
        
        token = stream.next_page_token(response)
        assert token == {"page": 2}
        
        # Last page - should return None
        response.json.return_value = {
            "meta": {
                "page": 3,
                "total_pages": 3
            }
        }
        
        token = stream.next_page_token(response)
        assert token is None
    
    def test_max_retries(self, config):
        """Test that max_retries is set to 0 (no retries)"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.max_retries == 0
    
    def test_parse_response_no_sleep_for_customers(self, config, customers_response):
        """Test that CustomersStream doesn't sleep (it overrides parse_response)"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        # Mock response
        response = MagicMock()
        response.json.return_value = customers_response
        
        # CustomersStream overrides parse_response completely and doesn't include sleep
        with patch('time.sleep') as mock_sleep:
            list(stream.parse_response(response))
            # Sleep should not be called since CustomersStream doesn't implement it
            mock_sleep.assert_not_called()


class TestCustomersStream:
    """Test CustomersStream functionality"""
    
    def test_stream_name(self, config):
        """Test stream name"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.name == "customers"
    
    def test_primary_key(self, config):
        """Test primary key is set correctly"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.primary_key == "id"
    
    def test_path(self, config):
        """Test API path"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.path() == "admin/customers.json"
    
    def test_parse_response(self, config, customers_response):
        """Test response parsing for customers"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        response = MagicMock()
        response.json.return_value = customers_response
        
        # Mock next_page_token to return None (last page)
        with patch.object(stream, 'next_page_token', return_value=None):
            records = list(stream.parse_response(response))
        
        assert len(records) == 1
        record = records[0]
        
        # Check ID is converted to integer
        assert record["id"] == 123
        assert isinstance(record["id"], int)
        
        # Check datetime conversions
        assert record["created_at"] == "2024-01-01T09:00:00"
        assert record["updated_at"] == "2025-01-15T16:00:00"
        assert record["first_order_completed_at"] == "2024-01-01T10:00:00"
        assert record["last_order_completed_at"] == "2025-01-15T15:30:00"
        assert record["point_expired_at"] == "2025-12-31T23:59:59"
        
        # Check date conversion
        assert record["birth"] == "1990-01-01"
        
        # Check removed fields are not present
        assert "type" not in record
        assert "name" not in record
        assert "name_kana" not in record
        assert "tel" not in record
        assert "mobile" not in record
        assert "is_auto_generated_email" not in record
        assert "accepts_marketing_updated_at" not in record
        
        # Check other fields are preserved
        assert record["email"] == "test@example.com"
        assert record["customer_rank_name"] == "ゴールド会員"
        assert record["buy_times"] == 5
        assert record["buy_total"] == 50000
    
    def test_get_json_schema(self, config):
        """Test JSON schema generation"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        schema = stream.get_json_schema()
        
        assert schema["type"] == "object"
        assert "id" in schema["required"]
        assert schema["properties"]["id"]["type"] == "integer"
        assert schema["properties"]["id"]["description"] == "顧客ID"
        
        # Check some field descriptions
        # Note: email field is filtered out, so we check other fields
        assert "customer_rank_name" in schema["properties"]
        assert schema["properties"]["birth"]["format"] == "date"
        assert schema["properties"]["created_at"]["format"] == "date-time"


class TestCustomerNotesStream:
    """Test CustomerNotesStream functionality"""
    
    def test_stream_name(self, config):
        """Test stream name"""
        stream = CustomerNotesStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.name == "customer_notes"
    
    def test_primary_key(self, config):
        """Test primary key is set correctly"""
        stream = CustomerNotesStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.primary_key == "id"
    
    def test_parse_response(self, config, customers_with_notes_response):
        """Test response parsing for customer notes"""
        stream = CustomerNotesStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        response = MagicMock()
        response.json.return_value = customers_with_notes_response
        
        records = list(stream.parse_response(response))
        
        assert len(records) == 2
        
        # Check first note
        note1 = records[0]
        assert note1["id"] == 456
        assert isinstance(note1["id"], int)
        assert note1["customer_id"] == 123
        assert isinstance(note1["customer_id"], int)
        assert note1["content"] == "初回購入のお客様"
        assert note1["created_at"] == "2024-01-01T10:30:00"
        assert note1["updated_at"] == "2024-01-01T10:30:00"
        assert note1["operated_at"] == "2024-01-01T10:00:00"
        
        # Check second note
        note2 = records[1]
        assert note2["id"] == 457
        assert note2["customer_id"] == 123
        assert note2["content"] == "VIP対応必要"
        assert "operated_at" not in note2  # This field is not in the response
    
    def test_parse_response_no_notes(self, config, empty_response):
        """Test response parsing when no notes exist"""
        stream = CustomerNotesStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        response = MagicMock()
        response.json.return_value = empty_response
        
        records = list(stream.parse_response(response))
        
        assert len(records) == 0
    
    def test_get_json_schema(self, config):
        """Test JSON schema generation"""
        stream = CustomerNotesStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        schema = stream.get_json_schema()
        
        assert schema["type"] == "object"
        assert "id" in schema["required"]
        assert schema["properties"]["id"]["type"] == "integer"
        assert schema["properties"]["id"]["description"] == "メモID"
        assert schema["properties"]["customer_id"]["type"] == ["integer", "null"]
        assert schema["properties"]["customer_id"]["description"] == "顧客ID"
        assert schema["properties"]["content"]["description"] == "メモ"