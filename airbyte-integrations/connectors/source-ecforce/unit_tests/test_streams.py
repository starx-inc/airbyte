import pytest
import requests
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timedelta
import time

from source_ecforce.source import (
    CustomersStream, 
    CustomerNotesStream,
    convert_ecforce_datetime,
    convert_ecforce_date,
    GCSHelper
)
from airbyte_cdk.models import SyncMode


class TestDateTimeConversion:
    """日付/時刻変換関数のテスト"""
    
    def test_convert_ecforce_datetime(self):
        """ecforce形式からISO 8601への日時変換のテスト"""
        assert convert_ecforce_datetime("2025/01/15 10:30:45") == "2025-01-15T10:30:45"
        assert convert_ecforce_datetime("2024/12/31 23:59:59") == "2024-12-31T23:59:59"
        assert convert_ecforce_datetime(None) is None
        assert convert_ecforce_datetime("") is None
        assert convert_ecforce_datetime("invalid") == "invalid"  # Returns original on parse error
    
    def test_convert_ecforce_date(self):
        """ecforce形式からISO 8601日付形式への変換のテスト"""
        assert convert_ecforce_date("1990/01/01") == "1990-01-01"
        assert convert_ecforce_date("2025/12/31") == "2025-12-31"
        assert convert_ecforce_date(None) is None
        assert convert_ecforce_date("") is None
        assert convert_ecforce_date("invalid") == "invalid"  # Returns original on parse error


class TestEcforceStream:
    """具体的な実装を通じてEcforceStreamの基本機能をテスト"""
    
    def test_url_base(self, config):
        """URLベースの構築のテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.url_base == f"https://{config['domain']}/api/v2/admin"
    
    def test_request_headers(self, config):
        """リクエストヘッダーに適切な認証情報が含まれているかテスト"""
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
        """リクエストパラメータに適切なフィルタが含まれているかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date="2025-01-01",
            api_token=config["api_token"]
        )
        
        # end_dateを手動で設定（テスト用）
        stream.end_date = "2025-01-31"
        
        params = stream.request_params(stream_state={})
        
        assert params["per"] == 100
        assert params["page"] == 1
        assert params["sort"] == "updated_at,id"
        assert params["lighter"] == 0
        assert params["q[updated_at_gteq]"] == "2025-01-01 00:00:00"
        assert params["q[updated_at_lt]"] == "2025-01-31 23:59:59"
    
    def test_request_params_with_pagination(self, config):
        """ページネーショントークン付きリクエストパラメータのテスト"""
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
        """次ページトークンの抽出のテスト"""
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
        """レート制限対応のためmax_retriesが3に設定されているかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.max_retries == 3
    
    def test_parse_response_with_request_interval(self, config, customers_response):
        """CustomersStreamのparse_responseがrequest_interval秒スリープするテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"],
            request_interval=2.5  # テスト用に2.5秒
        )
        
        # Mock response with next page
        response = MagicMock()
        response.json.return_value = customers_response
        
        # Mock next_page_token to return a value (simulating pagination)
        stream.next_page_token = MagicMock(return_value={"page": 2})
        
        with patch('time.sleep') as mock_sleep:
            list(stream.parse_response(response))
            # Should sleep with request_interval when there's a next page
            mock_sleep.assert_called_once_with(2.5)


class TestCustomersStream:
    """CustomersStreamの機能テスト"""
    
    def test_stream_name(self, config):
        """ストリーム名のテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.name == "customers"
    
    def test_primary_key(self, config):
        """プライマリキーが正しく設定されているかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.primary_key == "id"
    
    def test_path(self, config):
        """APIパスのテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        assert stream.path() == "admin/customers.json"
    
    def test_parse_response(self, config, customers_response):
        """顧客データのレスポンスパースのテスト"""
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
    
    def test_parse_response_with_gcs_save(self, config, customers_response):
        """ヘルパーが利用可能な場合、parse_responseがGCSにデータを保存するかテスト"""
        # GCSヘルパーをモック
        mock_gcs_helper = MagicMock(spec=GCSHelper)
        
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"],
            gcs_helper=mock_gcs_helper
        )
        
        response = MagicMock()
        response.json.return_value = customers_response
        
        # スライスを定義
        stream_slice = {"start_date": "2025-01-15", "end_date": "2025-01-15"}
        
        # next_page_tokenをモックしてNoneを返す（最後のページ）
        with patch.object(stream, 'next_page_token', return_value=None):
            list(stream.parse_response(response, stream_slice=stream_slice))
        
        # GCSに保存されたことを確認
        mock_gcs_helper.save_response.assert_called_once_with(
            "customers",
            "2025-01-15_2025-01-15_page1",
            customers_response
        )
    
    def test_parse_response_without_gcs(self, config, customers_response):
        """GCSヘルパーなしでparse_responseが動作するかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"],
            gcs_helper=None  # GCSヘルパーなし
        )
        
        response = MagicMock()
        response.json.return_value = customers_response
        
        # スライスを定義
        stream_slice = {"start_date": "2025-01-15", "end_date": "2025-01-15"}
        
        # next_page_tokenをモックしてNoneを返す（最後のページ）
        with patch.object(stream, 'next_page_token', return_value=None):
            records = list(stream.parse_response(response, stream_slice=stream_slice))
        
        # レコードが正常に処理されることを確認
        assert len(records) == 1
        assert records[0]["id"] == 123
    
    def test_get_json_schema(self, config):
        """JSONスキーマ生成のテスト"""
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


    def test_should_retry(self, config):
        """429エラーと5xxエラーのリトライ条件のテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        # 429エラーはリトライする
        response_429 = MagicMock()
        response_429.status_code = 429
        assert stream.should_retry(response_429) is True
        
        # 500エラーはリトライする
        response_500 = MagicMock()
        response_500.status_code = 500
        assert stream.should_retry(response_500) is True
        
        # 503エラーはリトライする
        response_503 = MagicMock()
        response_503.status_code = 503
        assert stream.should_retry(response_503) is True
        
        # 400エラーはリトライしない
        response_400 = MagicMock()
        response_400.status_code = 400
        assert stream.should_retry(response_400) is False
        
        # 200 OKはリトライしない
        response_200 = MagicMock()
        response_200.status_code = 200
        assert stream.should_retry(response_200) is False
    
    def test_backoff_time(self, config):
        """レート制限エラーのバックオフ時間計算のテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        # 429エラーでRetry-Afterヘッダーがある場合
        response_429_with_header = MagicMock()
        response_429_with_header.status_code = 429
        response_429_with_header.headers = {"Retry-After": "30"}
        assert stream.backoff_time(response_429_with_header) == 30.0
        
        # 429エラーでRetry-Afterヘッダーがない場合
        response_429_no_header = MagicMock()
        response_429_no_header.status_code = 429
        response_429_no_header.headers = {}
        assert stream.backoff_time(response_429_no_header) == 60.0  # デフォルト値
        
        # 500エラーの場合はNone（指数バックオフを使用）
        response_500 = MagicMock()
        response_500.status_code = 500
        assert stream.backoff_time(response_500) is None
    
    def test_parse_response_with_429_error(self, config):
        """parse_responseが429エラーで警告をログし例外を発生させるかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date=config["start_date"],
            api_token=config["api_token"]
        )
        
        # 429レスポンスをモック
        response = MagicMock()
        response.status_code = 429
        response.json.return_value = {"data": []}
        response.raise_for_status.side_effect = requests.HTTPError("429 Too Many Requests")
        
        # ロガーをモック
        with patch.object(stream.logger, 'warning') as mock_logger:
            # parse_responseが例外を発生させることを確認
            with pytest.raises(requests.HTTPError):
                list(stream.parse_response(response))
            
            # ログが出力されたことを確認
            mock_logger.assert_called_once()
            assert "Rate limit hit" in mock_logger.call_args[0][0]
        
        # raise_for_statusが呼ばれたことを確認
        response.raise_for_status.assert_called_once()


class TestIncrementalSync:
    """増分同期機能のテスト"""
    
    def test_supports_incremental(self, config):
        """ストリームが増分同期をサポートしているかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            api_token=config["api_token"]
        )
        
        assert stream.supports_incremental is True
        assert stream.cursor_field == "updated_at"
    
    def test_stream_slices_initial_sync(self, config):
        """初回同期時（stateなし）のストリームスライスのテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date="2025-01-15",
            api_token=config["api_token"]
        )
        
        # Manually set end_date for testing (複数月をまたぐケース)
        stream.end_date = "2025-03-10"
        
        slices = list(stream.stream_slices(sync_mode=SyncMode.incremental))
        
        assert len(slices) == 3
        assert slices[0] == {"start_date": "2025-01-15", "end_date": "2025-01-31"}
        assert slices[1] == {"start_date": "2025-02-01", "end_date": "2025-02-28"}
        assert slices[2] == {"start_date": "2025-03-01", "end_date": "2025-03-10"}
    
    def test_stream_slices_with_state(self, config):
        """既存stateがある場合のストリームスライスのテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date="2025-01-01",
            api_token=config["api_token"]
        )
        
        # Manually set end_date for testing (複数月をまたぐ)
        stream.end_date = "2025-03-15"
        
        # Simulate state from previous sync (1月末)
        stream_state = {"updated_at": "2025-01-31"}
        
        slices = list(stream.stream_slices(
            sync_mode=SyncMode.incremental,
            stream_state=stream_state
        ))
        
        # Should start from February (next day after state)
        assert len(slices) == 2
        assert slices[0] == {"start_date": "2025-02-01", "end_date": "2025-02-28"}
        assert slices[1] == {"start_date": "2025-03-01", "end_date": "2025-03-15"}
    
    def test_stream_slices_with_date_state(self, config):
        """日付形式state（タイムスタンプではない）のストリームスライスのテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date="2025-01-01",
            api_token=config["api_token"]
        )
        
        # Manually set end_date for testing (同じ月内)
        stream.end_date = "2025-01-20"
        
        # Simulate state from previous sync with date format (月の中間)
        stream_state = {"updated_at": "2025-01-15"}
        
        slices = list(stream.stream_slices(
            sync_mode=SyncMode.incremental,
            stream_state=stream_state
        ))
        
        # Should start from the day after the last synced date, within the same month
        assert len(slices) == 1
        assert slices[0] == {"start_date": "2025-01-16", "end_date": "2025-01-20"}
    
    def test_get_updated_state(self, config):
        """state更新ロジック - 月次更新のテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            api_token=config["api_token"]
        )
        
        # Set end_date for testing
        stream.end_date = "2025-02-15"
        
        current_state = {}
        
        # Test with record in January - should update to end of January
        january_record = {"updated_at": "2025-01-15T15:00:00", "id": 123}
        new_state = stream.get_updated_state(current_state, january_record)
        assert new_state["updated_at"] == "2025-01-31"  # End of January
        
        # Test with record in February - should update to end_date (Feb 15)
        current_state = {"updated_at": "2025-01-31"}
        february_record = {"updated_at": "2025-02-10T08:00:00", "id": 124}
        new_state = stream.get_updated_state(current_state, february_record)
        assert new_state["updated_at"] == "2025-02-15"  # end_date limit
    
    def test_request_params_with_slice(self, config):
        """ストリームスライス付きリクエストパラメータのテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            api_token=config["api_token"]
        )
        
        stream_slice = {"start_date": "2025-01-15", "end_date": "2025-01-15"}
        params = stream.request_params(
            stream_state={},
            stream_slice=stream_slice
        )
        
        assert params["q[updated_at_gteq]"] == "2025-01-15 00:00:00"
        assert params["q[updated_at_lt]"] == "2025-01-15 23:59:59"
    
    def test_default_start_date(self, config):
        """デフォルトの開始日が2年前になっているかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            api_token=config["api_token"]
        )
        
        # Check that start_date is set (2 years ago)
        expected_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        assert stream.start_date == expected_date
    
    def test_stream_slices_with_request_interval(self, config):
        """stream_slicesがrequest_interval秒待機するかテスト"""
        stream = CustomersStream(
            domain=config["domain"],
            start_date="2025-01-01",
            api_token=config["api_token"],
            request_interval=0.5  # テスト用に0.5秒
        )
        
        # Manually set end_date for testing (複数月をまたぐ)
        stream.end_date = "2025-03-10"
        
        with patch('time.sleep') as mock_sleep:
            slices = list(stream.stream_slices(sync_mode=SyncMode.incremental))
            
            # 3つのスライスがあり、2回スリープするはず（最初のスライスではスリープしない）
            assert len(slices) == 3
            assert mock_sleep.call_count == 2
            mock_sleep.assert_called_with(0.5)


class TestCustomerNotesStream:
    """CustomerNotesStreamの機能テスト"""
    
    def test_stream_name(self, config):
        """ストリーム名のテスト"""
        # 親ストリームをモック
        mock_parent = MagicMock(spec=CustomersStream)
        
        stream = CustomerNotesStream(
            parent=mock_parent
        )
        
        assert stream.name == "customer_notes"
    
    def test_primary_key(self, config):
        """プライマリキーが正しく設定されているかテスト"""
        # 親ストリームをモック
        mock_parent = MagicMock(spec=CustomersStream)
        
        stream = CustomerNotesStream(
            parent=mock_parent
        )
        
        assert stream.primary_key == "id"
    
    def test_parse_response(self, config, customers_with_notes_response):
        """顧客ノートのレスポンスパースのテスト"""
        # 親ストリームをモック
        mock_parent = MagicMock(spec=CustomersStream)
        mock_parent.name = "customers"
        mock_parent.gcs_helper = None
        
        stream = CustomerNotesStream(
            parent=mock_parent
        )
        
        # parse_responseメソッドはHttpSubStreamでは使われない
        # 代わりに_parse_notes_from_responseをテスト
        records = list(stream._parse_notes_from_response(customers_with_notes_response))
        
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
        """ノートが存在しない場合のレスポンスパースのテスト"""
        # 親ストリームをモック
        mock_parent = MagicMock(spec=CustomersStream)
        mock_parent.name = "customers"
        mock_parent.gcs_helper = None
        
        stream = CustomerNotesStream(
            parent=mock_parent
        )
        
        # _parse_notes_from_responseをテスト
        records = list(stream._parse_notes_from_response(empty_response))
        
        assert len(records) == 0
    
    def test_get_json_schema(self, config):
        """JSONスキーマ生成のテスト"""
        # 親ストリームをモック
        mock_parent = MagicMock(spec=CustomersStream)
        
        stream = CustomerNotesStream(
            parent=mock_parent
        )
        
        schema = stream.get_json_schema()
        
        assert schema["type"] == "object"
        assert "id" in schema["required"]
        assert schema["properties"]["id"]["type"] == "integer"
        assert schema["properties"]["id"]["description"] == "メモID"
        assert schema["properties"]["customer_id"]["type"] == ["integer", "null"]
        assert schema["properties"]["customer_id"]["description"] == "顧客ID"
        assert schema["properties"]["content"]["description"] == "メモ"
    
    def test_read_records_from_gcs(self, config, customers_with_notes_response):
        """GCSからのレコード読み取りのテスト"""
        # 親ストリームをモック
        mock_parent = MagicMock(spec=CustomersStream)
        mock_parent.name = "customers"
        
        # GCSヘルパーをモック
        mock_gcs_helper = MagicMock(spec=GCSHelper)
        mock_parent.gcs_helper = mock_gcs_helper
        
        # GCSから返すデータを設定
        mock_gcs_helper.load_response.side_effect = [
            customers_with_notes_response,  # ページ1
            None  # ページ2は存在しない
        ]
        
        stream = CustomerNotesStream(
            parent=mock_parent
        )
        
        # スライスを定義
        stream_slice = {"start_date": "2025-01-15", "end_date": "2025-01-15"}
        
        # read_recordsを実行
        records = list(stream.read_records(
            sync_mode=SyncMode.incremental,
            stream_slice=stream_slice
        ))
        
        # GCSから読み込まれたことを確認
        assert mock_gcs_helper.load_response.call_count == 2
        mock_gcs_helper.load_response.assert_any_call(
            "customers",
            "2025-01-15_2025-01-15_page1"
        )
        mock_gcs_helper.load_response.assert_any_call(
            "customers",
            "2025-01-15_2025-01-15_page2"
        )
        
        # 正しいノートが返されたことを確認
        assert len(records) == 2
        assert records[0]["id"] == 456
        assert records[0]["customer_id"] == 123
        assert records[0]["content"] == "初回購入のお客様"
        assert records[1]["id"] == 457
        assert records[1]["customer_id"] == 123
        assert records[1]["content"] == "VIP対応必要"
    
    def test_read_records_without_gcs(self, config):
        """GCSヘルパーがない場合、read_recordsが空を返すかテスト"""
        # 親ストリームをモック
        mock_parent = MagicMock(spec=CustomersStream)
        mock_parent.gcs_helper = None  # GCSヘルパーなし
        
        stream = CustomerNotesStream(
            parent=mock_parent
        )
        
        # スライスを定義
        stream_slice = {"start_date": "2025-01-15", "end_date": "2025-01-15"}
        
        # read_recordsを実行
        records = list(stream.read_records(
            sync_mode=SyncMode.incremental,
            stream_slice=stream_slice
        ))
        
        # 空の結果が返されることを確認
        assert len(records) == 0
