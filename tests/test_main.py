#!/usr/bin/env python3
"""
Tests for CI Rescue action
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import CIRescue, FailureInfo, OpenRouterClient


class TestOpenRouterClient(unittest.TestCase):
    """Test OpenRouter client functionality"""
    
    def setUp(self):
        self.client = OpenRouterClient("test-api-key", "test-model")
    
    def test_init(self):
        """Test client initialization"""
        self.assertEqual(self.client.api_key, "test-api-key")
        self.assertEqual(self.client.model, "test-model")
        self.assertEqual(self.client.base_url, "https://openrouter.ai/api/v1")
    
    @patch('requests.post')
    def test_analyze_failure_success(self, mock_post):
        """Test successful failure analysis"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test analysis result"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        failure_info = FailureInfo(
            job_name="test-job",
            step_name="test-step", 
            error_message="test error",
            logs="test logs",
            conclusion="failure"
        )
        
        result = self.client.analyze_failure(failure_info)
        self.assertEqual(result, "Test analysis result")
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_analyze_failure_error(self, mock_post):
        """Test failure analysis with API error"""
        mock_post.side_effect = Exception("API Error")
        
        failure_info = FailureInfo(
            job_name="test-job",
            step_name="test-step",
            error_message="test error", 
            logs="test logs",
            conclusion="failure"
        )
        
        result = self.client.analyze_failure(failure_info)
        self.assertIn("🚨 **CI Failure Analysis**", result)
        self.assertIn("Failed to analyze the error with AI", result)


class TestCIRescue(unittest.TestCase):
    """Test CI Rescue main functionality"""
    
    def setUp(self):
        # Mock environment variables
        self.env_vars = {
            'INPUT_GITHUB_TOKEN': 'test-token',
            'INPUT_OPENROUTER_API_KEY': 'test-openrouter-key',
            'INPUT_MODEL': 'test-model',
            'INPUT_MAX_TOKENS': '500',
            'INPUT_INCLUDE_LOGS': 'true',
            'INPUT_COMMENT_MODE': 'update-existing',
            'GITHUB_REPOSITORY': 'test/repo',
            'GITHUB_SHA': 'test-sha',
            'GITHUB_RUN_ID': '12345',
            'GITHUB_EVENT_NAME': 'pull_request'
        }
        
        with patch.dict(os.environ, self.env_vars):
            with patch('main.Github'), patch('main.OpenRouterClient'):
                self.rescue = CIRescue()
    
    def test_init_missing_vars(self):
        """Test initialization with missing environment variables"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                CIRescue()
    
    @patch('main.Github')
    @patch('main.OpenRouterClient')
    def test_init_success(self, mock_openrouter, mock_github):
        """Test successful initialization"""
        with patch.dict(os.environ, self.env_vars):
            rescue = CIRescue()
            self.assertEqual(rescue.github_token, 'test-token')
            self.assertEqual(rescue.openrouter_api_key, 'test-openrouter-key')
            self.assertEqual(rescue.model, 'test-model')
            self.assertEqual(rescue.max_tokens, 500)


class TestFailureInfo(unittest.TestCase):
    """Test FailureInfo dataclass"""
    
    def test_creation(self):
        """Test creating FailureInfo instance"""
        failure = FailureInfo(
            job_name="test-job",
            step_name="test-step",
            error_message="test error",
            logs="test logs", 
            conclusion="failure"
        )
        
        self.assertEqual(failure.job_name, "test-job")
        self.assertEqual(failure.step_name, "test-step")
        self.assertEqual(failure.error_message, "test error")
        self.assertEqual(failure.logs, "test logs")
        self.assertEqual(failure.conclusion, "failure")


if __name__ == '__main__':
    unittest.main()
