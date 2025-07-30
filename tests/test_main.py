#!/usr/bin/env python3
"""
Tests for CI Rescue action
"""

import unittest
from unittest.mock import Mock, patch
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import CIRescue, FailureInfo, OpenRouterClient


class TestOpenRouterClient(unittest.TestCase):
    """Test OpenRouter client functionality"""
    
    def setUp(self):
        self.client = OpenRouterClient("test-api-key", "test-model")

    def test_fail(self):
	self.assertEqual(1,2)
    
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
        
        # Use a fresh mock for each test
        self.patch_github = patch('main.Github')
        self.patch_openrouter = patch('main.OpenRouterClient')
        
        self.mock_github_class = self.patch_github.start()
        self.mock_openrouter_class = self.patch_openrouter.start()
        
        self.mock_github_instance = self.mock_github_class.return_value
        self.mock_openrouter_instance = self.mock_openrouter_class.return_value

        with patch.dict(os.environ, self.env_vars):
            self.rescue = CIRescue()
            self.rescue.github = self.mock_github_instance
            self.rescue.openrouter = self.mock_openrouter_instance

    def tearDown(self):
        self.patch_github.stop()
        self.patch_openrouter.stop()
    
    def test_init_missing_vars(self):
        """Test initialization with missing environment variables"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                CIRescue()
    
    def test_init_success(self):
        """Test successful initialization"""
        with patch.dict(os.environ, self.env_vars):
            self.assertIsInstance(self.rescue, CIRescue)
            self.assertEqual(self.rescue.github_token, 'test-token')
            self.assertEqual(self.rescue.openrouter_api_key, 'test-openrouter-key')
            self.assertEqual(self.rescue.model, 'test-model')
            self.assertEqual(self.rescue.max_tokens, 500)

    def test_parse_analysis_with_valid_annotations(self):
        """Test parsing analysis with a valid annotation block"""
        valid_annotation_json = '''{
          "annotations": [
            {"path": "src/main.py", "start_line": 10, "message": "Test annotation"}
          ]
        }'''
        analysis_text = f"This is the analysis.<<<CI-RESCUE-ANNOTATIONS>>>{valid_annotation_json}<<<CI-RESCUE-ANNOTATIONS>>>"
        
        comment, annotations = self.rescue._parse_analysis_with_annotations(analysis_text)
        
        self.assertEqual(comment, "This is the analysis.")
        self.assertIsNotNone(annotations)
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]['path'], 'src/main.py')

    def test_parse_analysis_no_annotations(self):
        """Test parsing analysis with no annotation block"""
        analysis_text = "This is a simple analysis with no annotations."
        comment, annotations = self.rescue._parse_analysis_with_annotations(analysis_text)
        self.assertEqual(comment, analysis_text)
        self.assertIsNone(annotations)

    def test_parse_analysis_malformed_json(self):
        """Test parsing analysis with malformed JSON in the annotation block"""
        malformed_json = '{"annotations": [{"path": "file.py"}]' # Missing closing brace
        analysis_text = f"Analysis.<<<CI-RESCUE-ANNOTATIONS>>>{malformed_json}<<<CI-RESCUE-ANNOTATIONS>>>"
        
        comment, annotations = self.rescue._parse_analysis_with_annotations(analysis_text)
        self.assertIn("Analysis.", comment)
        self.assertIn(malformed_json, comment) # Should return the original text
        self.assertIsNone(annotations)

    @patch('main.CIRescue.post_annotations')
    @patch('main.CIRescue.post_or_update_comment')
    def test_run_with_annotations(self, mock_post_comment, mock_post_annotations):
        """Test the main run loop correctly calls annotation methods"""
        # Mock failure data and PR
        self.rescue.get_workflow_run_failures = Mock(return_value=[FailureInfo('job', 'step', 'err', 'log', 'fail')])
        mock_pr = Mock()
        mock_pr.number = 123
        self.rescue.get_pull_request = Mock(return_value=mock_pr)
        
        # Mock AI response with annotations
        annotation_json = '''{
          "annotations": [{"path": "test.py", "start_line": 1, "message": "failure"}]
        }'''
        ai_response = f"Analysis here.<<<CI-RESCUE-ANNOTATIONS>>>{annotation_json}<<<CI-RESCUE-ANNOTATIONS>>>"
        self.mock_openrouter_instance.analyze_failure.return_value = ai_response

        self.rescue.run()

        # Verify that comment and annotation methods were called
        mock_post_comment.assert_called_once()
        mock_post_annotations.assert_called_once()
        # Check that the parsed annotations are passed correctly
        annotations_arg = mock_post_annotations.call_args[0][1]
        self.assertEqual(len(annotations_arg), 1)
        self.assertEqual(annotations_arg[0]['path'], 'test.py')

    def test_post_annotations_api_call(self):
        """Test that the GitHub check run API is called correctly"""
        mock_repo = Mock()
        self.mock_github_instance.get_repo.return_value = mock_repo
        
        mock_pr = Mock()
        mock_pr.head.sha = 'test-sha'
        mock_pr.number = 123

        annotations = [
            {"path": "file.py", "start_line": 1, "end_line": 1, "message": "Error", "annotation_level": "failure"}
        ]

        self.rescue.post_annotations(mock_pr, annotations)

        # Verify that create_check_run was called with the right data
        mock_repo.create_check_run.assert_called_once()
        call_kwargs = mock_repo.create_check_run.call_args[1]
        self.assertEqual(call_kwargs['name'], 'AI Failure Analysis')
        self.assertEqual(call_kwargs['head_sha'], 'test-sha')
        self.assertEqual(call_kwargs['conclusion'], 'failure')
        self.assertEqual(len(call_kwargs['output']['annotations']), 1)
        self.assertEqual(call_kwargs['output']['annotations'][0]['path'], 'file.py')


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
