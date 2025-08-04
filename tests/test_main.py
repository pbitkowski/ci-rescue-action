#!/usr/bin/env python3
"""
Tests for CI Rescue action
"""

import unittest
from unittest.mock import Mock, patch
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import CIRescue, FailureInfo, OpenRouterClient


class TestOpenRouterClient(unittest.TestCase):
    """Test OpenRouter client functionality"""

    def setUp(self):
        self.client = OpenRouterClient("test-api-key", "test-model")

    def test_initialization(self):
        """Test OpenRouterClient initialization"""
        client = OpenRouterClient("test-key", "test-model")
        self.assertEqual(client.api_key, "test-key")
        self.assertEqual(client.model, "test-model")
        self.assertEqual(client.base_url, "https://openrouter.ai/api/v1")

    def test_extract_error_context_empty_logs(self):
        """Test _extract_error_context with empty logs"""
        result = self.client._extract_error_context("")
        self.assertEqual(result, "No logs available")

    def test_extract_error_context_no_errors(self):
        """Test _extract_error_context when no error indicators are found"""
        logs = """Starting application
Loading configuration
Processing request
Application ready
Shutting down gracefully"""

        result = self.client._extract_error_context(logs)
        # Should return last 10 lines as fallback
        self.assertIn("Application ready", result)
        self.assertIn("Shutting down gracefully", result)

    def test_extract_error_context_single_error(self):
        """Test _extract_error_context with a single error"""
        logs = """Line 1: Starting process
Line 2: Loading module
Line 3: Initializing database
Line 4: Connecting to server
Line 5: Processing data
Line 6: ERROR: Connection timeout
Line 7: Retrying connection
Line 8: Failed to recover
Line 9: Shutting down
Line 10: Process ended"""

        result = self.client._extract_error_context(logs)

        # Should contain 5 lines before and 5 lines after the error
        self.assertIn("Line 1: Starting process", result)  # 5 lines before
        self.assertIn("Line 6: ERROR: Connection timeout", result)  # error line
        self.assertIn(
            "Line 10: Process ended", result
        )  # 5 lines after (only 4 available)

        # Should not contain extra lines
        lines = result.split("\n")
        self.assertEqual(len(lines), 10)  # 10 total lines in context

    def test_extract_error_context_multiple_errors_separate(self):
        """Test _extract_error_context with multiple separate errors"""
        logs = """Line 1: Starting
Line 2: ERROR: First error
Line 3: Recovery attempt
Line 4: Normal operation
Line 5: Normal operation
Line 6: Normal operation
Line 7: Normal operation
Line 8: Normal operation
Line 9: Normal operation
Line 10: Normal operation
Line 11: Normal operation
Line 12: Normal operation
Line 13: FAILED: Second error
Line 14: Cleanup
Line 15: Finished"""

        result = self.client._extract_error_context(logs)

        # Should contain two separate context blocks
        self.assertIn("---", result)  # Separator between blocks
        self.assertIn("ERROR: First error", result)
        self.assertIn("FAILED: Second error", result)

    def test_extract_error_context_overlapping_errors(self):
        """Test _extract_error_context with overlapping error contexts"""
        logs = """Line 1: Starting
Line 2: Loading
Line 3: ERROR: First error
Line 4: Processing
Line 5: FAILED: Second error  
Line 6: Recovery
Line 7: Finished"""

        result = self.client._extract_error_context(logs)

        # Should merge overlapping ranges into one block
        self.assertNotIn("---", result)  # No separator since ranges merged
        self.assertIn("ERROR: First error", result)
        self.assertIn("FAILED: Second error", result)

        # Should contain all lines since they're close together
        lines = result.split("\n")
        self.assertEqual(len(lines), 7)  # All 7 lines included

    def test_extract_error_context_case_insensitive(self):
        """Test case-insensitive error detection"""
        logs = """Line 1: Starting
Line 2: error: lowercase error
Line 3: Normal
Line 4: Error: Mixed case error
Line 5: Normal
Line 6: ERROR: Uppercase error
Line 7: Finished"""

        result = self.client._extract_error_context(logs)

        # Should find all three error variations
        self.assertIn("error: lowercase error", result)
        self.assertIn("Error: Mixed case error", result)
        self.assertIn("ERROR: Uppercase error", result)

    def test_extract_error_context_different_indicators(self):
        """Test different types of error indicators"""
        logs = """Line 1: Starting
Line 2: Exception: Runtime exception
Line 3: Normal
Line 4: Traceback (most recent call last):
Line 5: Normal
Line 6: SyntaxError: Invalid syntax
Line 7: Normal
Line 8: ##[error] GitHub Actions error
Line 9: Normal
Line 10: FAILURE: Build failed
Line 11: Finished"""

        result = self.client._extract_error_context(logs)

        # Should detect various error types
        self.assertIn("Exception: Runtime exception", result)
        self.assertIn("Traceback", result)
        self.assertIn("SyntaxError", result)
        self.assertIn("##[error]", result)
        self.assertIn("FAILURE:", result)

    def test_extract_error_context_error_at_start(self):
        """Test error at the very beginning of logs"""
        logs = """ERROR: Error at start
Line 2: Recovery
Line 3: Normal
Line 4: Normal
Line 5: Normal
Line 6: Finished"""

        result = self.client._extract_error_context(logs)

        # Should handle error at start gracefully (no lines before)
        self.assertIn("ERROR: Error at start", result)
        self.assertIn("Line 6: Finished", result)  # Should still get 5 lines after

    def test_extract_error_context_error_at_end(self):
        """Test error at the very end of logs"""
        logs = """Line 1: Starting
Line 2: Normal
Line 3: Normal
Line 4: Normal
Line 5: Normal
Line 6: ERROR: Error at end"""

        result = self.client._extract_error_context(logs)

        # Should handle error at end gracefully (no lines after)
        self.assertIn("Line 1: Starting", result)  # Should get 5 lines before
        self.assertIn("ERROR: Error at end", result)

    def test_extract_error_context_whitespace_handling(self):
        """Test proper whitespace handling with rstrip()"""
        logs = """Line 1: Normal    
Line 2: ERROR: Error with trailing spaces   \t
Line 3: Normal\n\n
Line 4: Finished"""

        result = self.client._extract_error_context(logs)

        # Should remove trailing whitespace but preserve structure
        lines = result.split("\n")
        for line in lines:
            self.assertFalse(line.endswith(" "))  # No trailing spaces
            self.assertFalse(line.endswith("\t"))  # No trailing tabs

        self.assertIn("ERROR: Error with trailing spaces", result)

    def test_extract_error_context_limit_blocks(self):
        """Test limiting to max 3 context blocks"""
        # Create logs with 5 separate errors (far apart)
        logs_parts = []
        for i in range(5):
            logs_parts.append(f"Section {i + 1} start")
            for j in range(10):  # Add padding lines
                logs_parts.append(f"Section {i + 1} line {j + 1}")
            logs_parts.append(f"ERROR: Error {i + 1}")
            for j in range(10):  # Add more padding
                logs_parts.append(f"Section {i + 1} end line {j + 1}")

        logs = "\n".join(logs_parts)
        result = self.client._extract_error_context(logs)

        # Should only contain last 3 errors
        self.assertNotIn("ERROR: Error 1", result)
        self.assertNotIn("ERROR: Error 2", result)
        self.assertIn("ERROR: Error 3", result)
        self.assertIn("ERROR: Error 4", result)
        self.assertIn("ERROR: Error 5", result)

        # Should have 2 separators (3 blocks)
        self.assertEqual(result.count("---"), 2)

    def test_init(self):
        """Test client initialization"""
        self.assertEqual(self.client.api_key, "test-api-key")
        self.assertEqual(self.client.model, "test-model")
        self.assertEqual(self.client.base_url, "https://openrouter.ai/api/v1")

    @patch("requests.post")
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
            conclusion="failure",
        )

        result = self.client.analyze_failure(failure_info)
        self.assertEqual(result, "Test analysis result")
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_analyze_failure_error(self, mock_post):
        """Test failure analysis with API error"""
        mock_post.side_effect = Exception("API Error")

        failure_info = FailureInfo(
            job_name="test-job",
            step_name="test-step",
            error_message="test error",
            logs="test logs",
            conclusion="failure",
        )

        result = self.client.analyze_failure(failure_info)
        self.assertIn("🚨 **CI Failure Analysis**", result)
        self.assertIn("Failed to analyze the error with AI", result)


class TestCIRescue(unittest.TestCase):
    """Test CI Rescue main functionality"""

    def setUp(self):
        # Mock environment variables
        self.env_vars = {
            "INPUT_GITHUB_TOKEN": "test-token",
            "INPUT_OPENROUTER_API_KEY": "test-openrouter-key",
            "INPUT_MODEL": "test-model",
            "INPUT_MAX_TOKENS": "500",
            "INPUT_INCLUDE_LOGS": "true",
            "INPUT_COMMENT_MODE": "update-existing",
            "GITHUB_REPOSITORY": "test/repo",
            "GITHUB_SHA": "test-sha",
            "GITHUB_RUN_ID": "12345",
            "GITHUB_EVENT_NAME": "pull_request",
        }

        # Use a fresh mock for each test
        self.patch_github = patch("main.Github")
        self.patch_openrouter = patch("main.OpenRouterClient")

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
            self.assertEqual(self.rescue.github_token, "test-token")
            self.assertEqual(self.rescue.openrouter_api_key, "test-openrouter-key")
            self.assertEqual(self.rescue.model, "test-model")
            self.assertEqual(self.rescue.max_tokens, 500)

    def test_parse_analysis_with_valid_annotations(self):
        """Test parsing analysis with a valid annotation block"""
        valid_annotation_json = """{
          "annotations": [
            {"path": "src/main.py", "start_line": 10, "message": "Test annotation"}
          ]
        }"""
        analysis_text = f"This is the analysis.<<<CI-RESCUE-ANNOTATIONS>>>{valid_annotation_json}<<<CI-RESCUE-ANNOTATIONS>>>"

        comment, annotations = self.rescue._parse_analysis_with_annotations(
            analysis_text
        )

        self.assertEqual(comment, "This is the analysis.")
        self.assertIsNotNone(annotations)
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["path"], "src/main.py")

    def test_parse_analysis_no_annotations(self):
        """Test parsing analysis with no annotation block"""
        analysis_text = "This is a simple analysis with no annotations."
        comment, annotations = self.rescue._parse_analysis_with_annotations(
            analysis_text
        )
        self.assertEqual(comment, analysis_text)
        self.assertIsNone(annotations)

    def test_parse_analysis_malformed_json(self):
        """Test parsing analysis with malformed JSON in the annotation block"""
        malformed_json = (
            '{"annotations": [{"path": "file.py"}]'  # Missing closing brace
        )
        analysis_text = f"Analysis.<<<CI-RESCUE-ANNOTATIONS>>>{malformed_json}<<<CI-RESCUE-ANNOTATIONS>>>"

        comment, annotations = self.rescue._parse_analysis_with_annotations(
            analysis_text
        )
        self.assertIn("Analysis.", comment)
        self.assertIn(malformed_json, comment)  # Should return the original text
        self.assertIsNone(annotations)

    @patch("main.CIRescue.post_line_annotations")
    @patch("main.CIRescue.post_or_update_comment")
    def test_run_with_annotations(self, mock_post_comment, mock_post_line_annotations):
        """Test the main run loop correctly calls annotation methods"""
        # Mock failure data and PR
        self.rescue.get_workflow_run_failures = Mock(
            return_value=[FailureInfo("job", "step", "err", "log", "fail")]
        )
        mock_pr = Mock()
        mock_pr.number = 123
        self.rescue.get_pull_request = Mock(return_value=mock_pr)

        # Mock AI response with annotations
        annotation_json = """{
          "annotations": [{"path": "test.py", "start_line": 1, "message": "failure"}]
        }"""
        ai_response = f"Analysis here.<<<CI-RESCUE-ANNOTATIONS>>>{annotation_json}<<<CI-RESCUE-ANNOTATIONS>>>"
        self.mock_openrouter_instance.analyze_failure.return_value = ai_response

        self.rescue.run()

        # Verify that comment and line annotation methods were called
        mock_post_comment.assert_called_once()
        mock_post_line_annotations.assert_called_once()

        # Check that the comment includes formatted annotations
        comment_arg = mock_post_comment.call_args[0][1]
        self.assertIn("Code Annotations", comment_arg)
        self.assertIn("test.py", comment_arg)

        # Check that the parsed annotations are passed to line annotations
        annotations_arg = mock_post_line_annotations.call_args[0][1]
        self.assertEqual(len(annotations_arg), 1)
        self.assertEqual(annotations_arg[0]["path"], "test.py")

    def test_post_line_annotations_api_call(self):
        """Test that the GitHub review API is called correctly for line annotations"""
        mock_pr = Mock()
        mock_pr.head.sha = "test-sha"
        mock_pr.number = 123
        mock_commits = Mock()
        mock_commits.reversed = [Mock()]  # Mock commit list
        mock_pr.get_commits.return_value = mock_commits
        mock_pr.create_review.return_value = Mock(id=456)

        annotations = [
            {
                "path": "file.py",
                "start_line": 1,
                "message": "Error",
                "annotation_level": "failure",
            }
        ]

        self.rescue.post_line_annotations(mock_pr, annotations)

        # Verify that create_review was called with the right data
        mock_pr.create_review.assert_called_once()
        call_kwargs = mock_pr.create_review.call_args[1]
        self.assertEqual(call_kwargs["event"], "COMMENT")
        self.assertEqual(len(call_kwargs["comments"]), 1)
        self.assertEqual(call_kwargs["comments"][0]["path"], "file.py")
        self.assertEqual(call_kwargs["comments"][0]["line"], 1)
        self.assertIn("CI Rescue Analysis", call_kwargs["comments"][0]["body"])

    def test_format_annotations_for_comment(self):
        """Test formatting annotations for inclusion in PR comment"""
        annotations = [
            {
                "path": "test.py",
                "start_line": 10,
                "message": "Test error",
                "annotation_level": "failure",
            }
        ]

        formatted = self.rescue.format_annotations_for_comment(annotations)

        self.assertIn("Code Annotations", formatted)
        self.assertIn("test.py", formatted)
        self.assertIn("Line 10", formatted)
        self.assertIn("Test error", formatted)
        self.assertIn("❌", formatted)  # failure emoji


class TestFailureInfo(unittest.TestCase):
    """Test FailureInfo dataclass"""

    def test_creation(self):
        """Test creating FailureInfo instance"""
        failure = FailureInfo(
            job_name="test-job",
            step_name="test-step",
            error_message="test error",
            logs="test logs",
            conclusion="failure",
        )

        self.assertEqual(failure.job_name, "test-job")
        self.assertEqual(failure.step_name, "test-step")
        self.assertEqual(failure.error_message, "test error")
        self.assertEqual(failure.logs, "test logs")
        self.assertEqual(failure.conclusion, "failure")


if __name__ == "__main__":
    unittest.main()
