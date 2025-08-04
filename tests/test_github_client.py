#!/usr/bin/env python3
"""
Tests for GitHub client functionality
"""

import unittest
from unittest.mock import Mock, patch
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from github_client import GitHubClient

class TestGitHubClient(unittest.TestCase):
    """Test GitHub client functionality"""

    def setUp(self):
        # Mock environment variables
        self.env_vars = {
            "INPUT_GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "test/repo", 
            "GITHUB_RUN_ID": "12345",
            "GITHUB_SHA": "test-sha",
        }

        # Start patches
        self.env_patcher = patch.dict(os.environ, self.env_vars)
        self.github_patcher = patch("github_client.Github")
        
        self.env_patcher.start()
        self.mock_github = self.github_patcher.start()
        
        self.client = GitHubClient(
            os.getenv("INPUT_GITHUB_TOKEN"),
            os.getenv("GITHUB_REPOSITORY"),
            os.getenv("GITHUB_RUN_ID"),
        )

    def tearDown(self):
        self.env_patcher.stop()
        self.github_patcher.stop()

    def test_failing_scenario(self):
        self.assertEqual(1, 2)

    def test_post_line_annotations_api_call(self):
        """Test that the GitHub review API is called correctly for line annotations"""
        mock_pr = Mock()
        mock_pr.head.sha = "test-sha"
        mock_pr.number = 123
        mock_commits = Mock()
        mock_commits.reversed = [Mock()]  # Mock commit list
        mock_pr.get_commits.return_value = mock_commits
        mock_pr.create_review.return_value = Mock(id=456)

        review_comments = [
            {
                "path": "file.py",
                "line": 1,
                "body": "❌ **CI Rescue Analysis**\n\nError message",
            }
        ]

        # Mock get_review_comments for cleanup
        mock_pr.get_review_comments.return_value = []
        
        self.client.post_line_annotations(mock_pr, review_comments)

        # Verify that cleanup was called
        mock_pr.get_review_comments.assert_called_once()
        
        # Verify that create_review was called with the right data
        mock_pr.create_review.assert_called_once()
        call_kwargs = mock_pr.create_review.call_args[1]
        self.assertEqual(call_kwargs["event"], "COMMENT")
        self.assertEqual(len(call_kwargs["comments"]), 1)
        self.assertEqual(call_kwargs["comments"][0]["path"], "file.py")
        self.assertEqual(call_kwargs["comments"][0]["line"], 1)
        # Import the constant for testing
        from constants import CI_ANNOTATION_MARKER
        self.assertIn(CI_ANNOTATION_MARKER, call_kwargs["comments"][0]["body"])

    @patch("requests.get")
    def test_get_workflow_run_failures(self, mock_get):
        """Test getting workflow run failures"""
        # Mock the API response for jobs
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [{
                "id": 123,
                "name": "test-job",
                "conclusion": "failure",
                "steps": [{"name": "test-step", "conclusion": "failure"}]
            }]
        }
        mock_get.return_value = mock_response
        
        # Mock the get_job_logs method
        with patch.object(self.client, 'get_job_logs', return_value="test logs"):
            failures = self.client.get_workflow_run_failures()
            
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].job_name, "test-job")
        self.assertEqual(failures[0].step_name, "test-step")
        self.assertEqual(failures[0].logs, "test logs")

    def test_get_pull_request(self):
        """Test getting pull request for workflow run"""
        # Simple mock setup - just set sha and event_name
        self.client.sha = "test-sha"
        self.client.event_name = "push"  # Use non-PR event for simplicity
        
        mock_repo = Mock()
        mock_pr = Mock()
        mock_pr.head.sha = "test-sha"  # Match the client sha
        
        # Mock the github client
        self.client.github.get_repo.return_value = mock_repo
        mock_repo.get_pulls.return_value = [mock_pr]
        
        pr = self.client.get_pull_request()
        
        self.assertEqual(pr, mock_pr)

    def test_post_or_update_comment(self):
        """Test posting or updating PR comment"""
        mock_pr = Mock()
        mock_pr.get_issue_comments.return_value = []
        
        self.client.post_or_update_comment(mock_pr, "Test comment")
        
        # Should create new comment when none exist
        from constants import CI_RESCUE_COMMENT_MARKER
        expected_body = f"{CI_RESCUE_COMMENT_MARKER}\nTest comment"
        mock_pr.create_issue_comment.assert_called_once_with(expected_body)

    def test_remove_previous_ci_rescue_annotations(self):
        """Test removing previous CI Rescue annotation comments"""
        mock_pr = Mock()
        
        # Mock previous CI Rescue comments
        from constants import CI_ANNOTATION_MARKER
        
        mock_comment1 = Mock()
        mock_comment1.body = f"❌ **{CI_ANNOTATION_MARKER}**\n\nPrevious error"
        mock_comment1.path = "file1.py"
        mock_comment1.line = 10
        
        mock_comment2 = Mock()
        mock_comment2.body = "Some other comment"  # Not a CI Rescue comment
        
        mock_comment3 = Mock()
        mock_comment3.body = f"🚨 **{CI_ANNOTATION_MARKER}**\n\nAnother previous error"
        mock_comment3.path = "file2.py"
        mock_comment3.line = 20
        
        mock_pr.get_review_comments.return_value = [mock_comment1, mock_comment2, mock_comment3]
        
        # Call the cleanup method
        self.client.remove_previous_ci_rescue_annotations(mock_pr)
        
        # Verify only CI Rescue comments were deleted
        mock_comment1.delete.assert_called_once()
        mock_comment3.delete.assert_called_once()
        mock_comment2.delete.assert_not_called()  # Should not delete non-CI-Rescue comments


if __name__ == "__main__":
    unittest.main()

