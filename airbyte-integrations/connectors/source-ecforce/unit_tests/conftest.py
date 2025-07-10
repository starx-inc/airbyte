import pytest
from typing import Dict, Any


@pytest.fixture
def config() -> Dict[str, Any]:
    """Test configuration fixture"""
    return {
        "domain": "test.ec-force.com",
        "api_token": "test-token-123",
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "include_notes": True
    }


@pytest.fixture
def customers_response() -> Dict[str, Any]:
    """Sample customers API response"""
    return {
        "data": [
            {
                "id": "123",
                "type": "customer",
                "attributes": {
                    "id": 123,
                    "authentication_token": "auth-token-123",
                    "number": "CUST001",
                    "state": "member",
                    "human_state_name": "会員",
                    "customer_rank_name": "ゴールド会員",
                    "email": "test@example.com",
                    "sex_id": 1,
                    "sex": "男性",
                    "job": "エンジニア",
                    "birth": "1990/01/01",
                    "buy_times": 5,
                    "buy_total": 50000,
                    "first_order_completed_at": "2024/01/01 10:00:00",
                    "last_order_completed_at": "2025/01/15 15:30:00",
                    "point": 1000,
                    "point_expired_at": "2025/12/31 23:59:59",
                    "customer_type_name": "一般顧客",
                    "optin": True,
                    "line_id": "LINE123",
                    "tenant_id": 1,
                    "mail_delivery_stop": False,
                    "np_royal_customer": False,
                    "blacklist": False,
                    "blacklist_reasons": "",
                    "labels": "VIP,リピーター",
                    "coupon_codes": "SAVE10,WELCOME20",
                    "link_number": "LINK001",
                    "created_at": "2024/01/01 09:00:00",
                    "updated_at": "2025/01/15 16:00:00",
                    "deleted_at": None,
                    # Fields to be removed
                    "type": "customer",
                    "name": "テスト太郎",
                    "name_kana": "テストタロウ",
                    "tel": "03-1234-5678",
                    "mobile": "090-1234-5678",
                    "is_auto_generated_email": False,
                    "accepts_marketing_updated_at": "2025/01/01 10:00:00"
                }
            }
        ],
        "included": [
            {
                "id": "456",
                "type": "note",
                "attributes": {
                    "content": "初回購入のお客様",
                    "created_at": "2024/01/01 10:30:00",
                    "updated_at": "2024/01/01 10:30:00",
                    "operated_at": "2024/01/01 10:00:00"
                }
            }
        ],
        "meta": {
            "total_count": 100,
            "page": 1,
            "per": 100,
            "count": 1,
            "total_pages": 1
        }
    }


@pytest.fixture
def customers_with_notes_response() -> Dict[str, Any]:
    """Sample customers API response with notes included"""
    return {
        "data": [
            {
                "id": "123",
                "type": "customer",
                "attributes": {
                    "id": 123,
                    "number": "CUST001",
                    "email": "test@example.com",
                    "created_at": "2024/01/01 09:00:00",
                    "updated_at": "2025/01/15 16:00:00"
                },
                "relationships": {
                    "notes": {
                        "data": [
                            {"id": "456", "type": "note"},
                            {"id": "457", "type": "note"}
                        ]
                    }
                }
            }
        ],
        "included": [
            {
                "id": "456",
                "type": "note",
                "attributes": {
                    "content": "初回購入のお客様",
                    "created_at": "2024/01/01 10:30:00",
                    "updated_at": "2024/01/01 10:30:00",
                    "operated_at": "2024/01/01 10:00:00"
                }
            },
            {
                "id": "457",
                "type": "note",
                "attributes": {
                    "content": "VIP対応必要",
                    "created_at": "2024/02/01 11:00:00",
                    "updated_at": "2024/02/01 11:00:00"
                }
            }
        ],
        "meta": {
            "total_count": 1,
            "page": 1,
            "per": 100,
            "count": 1,
            "total_pages": 1
        }
    }


@pytest.fixture
def empty_response() -> Dict[str, Any]:
    """Empty API response"""
    return {
        "data": [],
        "included": [],
        "meta": {
            "total_count": 0,
            "page": 1,
            "per": 100,
            "count": 0,
            "total_pages": 0
        }
    }
