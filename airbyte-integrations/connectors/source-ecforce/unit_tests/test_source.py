import pytest
from unittest.mock import MagicMock, patch
from source_ecforce.source import SourceEcforce


class TestSourceEcforce:
    """SourceEcforceのテスト"""
    
    def test_check_connection_success(self, config, customers_response):
        """接続チェックが成功するケースのテスト"""
        source = SourceEcforce()
        
        # ストリームのread_recordsメソッドをモック
        with patch('source_ecforce.source.CustomersStream.read_records') as mock_read:
            mock_read.return_value = iter([{"id": 123}])
            
            success, error = source.check_connection(MagicMock(), config)
            
            assert success is True
            assert error is None
    
    def test_check_connection_no_records(self, config, empty_response):
        """レコードがない場合の接続チェック（それでも成功）のテスト"""
        source = SourceEcforce()
        
        with patch('source_ecforce.source.CustomersStream.read_records') as mock_read:
            mock_read.return_value = iter([])
            
            success, error = source.check_connection(MagicMock(), config)
            
            assert success is True
            assert error is None
    
    def test_check_connection_failure(self, config):
        """接続チェックが失敗するケースのテスト"""
        source = SourceEcforce()
        
        with patch('source_ecforce.source.CustomersStream.read_records') as mock_read:
            mock_read.side_effect = Exception("API Error: 401 Unauthorized")
            
            success, error = source.check_connection(MagicMock(), config)
            
            assert success is False
            assert "Unable to connect to ecforce API: API Error: 401 Unauthorized" in error
    
    def test_streams_without_notes(self, config):
        """include_notesがFalseの場合、streamsメソッドがcustomersストリームのみ返すかテスト"""
        source = SourceEcforce()
        config["include_notes"] = False
        
        streams = source.streams(config)
        
        assert len(streams) == 1
        assert streams[0].name == "customers"
    
    def test_streams_with_notes(self, config):
        """include_notesがTrueの場合、streamsメソッドが両方のストリームを返すかテスト"""
        source = SourceEcforce()
        config["include_notes"] = True
        
        streams = source.streams(config)
        
        assert len(streams) == 2
        assert streams[0].name == "customers"
        assert streams[1].name == "customer_notes"
    
    def test_streams_configuration(self, config):
        """提供された設定でストリームが正しく構成されているかテスト"""
        source = SourceEcforce()
        
        streams = source.streams(config)
        
        customers_stream = streams[0]
        assert customers_stream.domain == config["domain"]
        assert customers_stream.api_token == config["api_token"]
        assert customers_stream.start_date == config["start_date"]
        # end_dateは提供されない場合、自動的に日本時間の昨日に設定される
        assert customers_stream.end_date is not None
        assert customers_stream.gcs_helper is None  # GCS設定が提供されていない
    
    def test_streams_with_gcs(self, config_with_gcs):
        """GCS設定でストリームが正しく構成されているかテスト"""
        source = SourceEcforce()
        
        with patch('source_ecforce.source.GCSHelper') as mock_gcs_helper:
            mock_gcs_instance = MagicMock()
            mock_gcs_helper.return_value = mock_gcs_instance
            
            streams = source.streams(config_with_gcs)
            
            # GCSHelperが正しいパラメータで初期化されたか検証
            mock_gcs_helper.assert_called_once_with(
                bucket_name="test-bucket",
                service_account_key='{"type": "service_account", "project_id": "test-project"}',
                connection_id="default"
            )
            
            # ストリームがGCSヘルパーを持っているか検証
            customers_stream = streams[0]
            assert customers_stream.gcs_helper == mock_gcs_instance
