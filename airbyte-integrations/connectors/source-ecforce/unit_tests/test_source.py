import pytest
from unittest.mock import MagicMock, patch
from source_ecforce.source import SourceEcforce


class TestSourceEcforce:
    """Tests for SourceEcforce"""
    
    def test_check_connection_success(self, config, customers_response):
        """Test successful connection check"""
        source = SourceEcforce()
        
        # Mock the stream's read_records method
        with patch('source_ecforce.source.CustomersStream.read_records') as mock_read:
            mock_read.return_value = iter([{"id": 123}])
            
            success, error = source.check_connection(MagicMock(), config)
            
            assert success is True
            assert error is None
    
    def test_check_connection_no_records(self, config, empty_response):
        """Test connection check with no records (still successful)"""
        source = SourceEcforce()
        
        with patch('source_ecforce.source.CustomersStream.read_records') as mock_read:
            mock_read.return_value = iter([])
            
            success, error = source.check_connection(MagicMock(), config)
            
            assert success is True
            assert error is None
    
    def test_check_connection_failure(self, config):
        """Test connection check failure"""
        source = SourceEcforce()
        
        with patch('source_ecforce.source.CustomersStream.read_records') as mock_read:
            mock_read.side_effect = Exception("API Error: 401 Unauthorized")
            
            success, error = source.check_connection(MagicMock(), config)
            
            assert success is False
            assert "Unable to connect to ecforce API: API Error: 401 Unauthorized" in error
    
    def test_streams_without_notes(self, config):
        """Test streams method returns only customers stream when include_notes is False"""
        source = SourceEcforce()
        config["include_notes"] = False
        
        streams = source.streams(config)
        
        assert len(streams) == 1
        assert streams[0].name == "customers"
    
    def test_streams_with_notes(self, config):
        """Test streams method returns both streams when include_notes is True"""
        source = SourceEcforce()
        config["include_notes"] = True
        
        streams = source.streams(config)
        
        assert len(streams) == 2
        assert streams[0].name == "customers"
        assert streams[1].name == "customer_notes"
    
    def test_streams_configuration(self, config):
        """Test that streams are properly configured with provided config"""
        source = SourceEcforce()
        
        streams = source.streams(config)
        
        for stream in streams:
            assert stream.domain == config["domain"]
            assert stream.api_token == config["api_token"]
            assert stream.start_date == config["start_date"]
            assert stream.end_date == config["end_date"]