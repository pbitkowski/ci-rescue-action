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
        
        # Verify that individual create_review_comment was called (Strategy 1)
        mock_pr.create_review_comment.assert_called_once()
        call_kwargs = mock_pr.create_review_comment.call_args[1]
        self.assertEqual(call_kwargs["path"], "file.py")
        self.assertEqual(call_kwargs["line"], 1)
        # Import the constant for testing
        from constants import CI_ANNOTATION_MARKER
        self.assertIn(CI_ANNOTATION_MARKER, call_kwargs["body"])

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

    def test_post_line_annotations_diff_validation_error(self):
        """Test handling of 'line must be part of diff' error"""
        mock_pr = Mock()
        mock_pr.get_review_comments.return_value = []
        mock_pr.get_commits.return_value.reversed = [Mock()]
        mock_pr.base.repo.full_name = "owner/repo"
        mock_pr.head.ref = "feature-branch"
        
        # Mock individual comment creation - one succeeds, one fails due to diff
        def mock_create_review_comment(**kwargs):
            if kwargs['line'] == 1:
                return Mock()  # Success
            else:
                raise Exception("pull_request_review_thread.line must be part of the diff")
        
        mock_pr.create_review_comment.side_effect = mock_create_review_comment
        
        review_comments = [
            {"path": "file1.py", "line": 1, "body": "Valid comment"},
            {"path": "file2.py", "line": 999, "body": "Invalid line comment"}
        ]
        
        # Should not raise exception, should handle gracefully
        self.client.post_line_annotations(mock_pr, review_comments)
        
        # Verify Strategy 1: individual line comments were attempted
        self.assertEqual(mock_pr.create_review_comment.call_count, 2)
        
        # Verify Strategy 2: fallback PR comment was created for the failed one
        self.assertEqual(mock_pr.create_issue_comment.call_count, 1)

    def test_fallback_pr_comments_with_editor_links(self):
        """Test fallback Strategy 2 that creates PR comments with editor links"""
        mock_pr = Mock()
        mock_pr.get_review_comments.return_value = []
        mock_pr.get_commits.return_value.reversed = [Mock()]
        mock_pr.base.repo.full_name = "owner/repo"
        mock_pr.head.ref = "feature-branch"
        
        # Mock all in-line comments to fail so we get to Strategy 2 fallback
        mock_pr.create_review_comment.side_effect = Exception("line must be part of the diff")
        
        review_comments = [
            {"path": "src/main.py", "line": 42, "body": "**CI Rescue Analysis**: Fix this issue"},
            {"path": "tests/test.py", "line": 123, "body": "**CI Rescue Analysis**: Add test case"}
        ]
        
        # Should not raise exception, should create fallback PR comments
        self.client.post_line_annotations(mock_pr, review_comments)
        
        # Verify Strategy 1: in-line comments were attempted
        self.assertEqual(mock_pr.create_review_comment.call_count, 2)
        
        # Verify Strategy 2: fallback PR comments were created
        self.assertEqual(mock_pr.create_issue_comment.call_count, 2)
        
        # Check the first fallback comment content
        first_call_args = mock_pr.create_issue_comment.call_args_list[0][0][0]
        self.assertIn("🔧 CI Rescue Analysis", first_call_args)
        self.assertIn("src/main.py", first_call_args)
        self.assertIn("**📍 Line:** `42`", first_call_args)
        self.assertIn("https://github.dev/owner/repo/blob/feature-branch/src/main.py#L42", first_call_args)
        self.assertIn("cursor://file/owner/repo/src/main.py:42", first_call_args)
        self.assertIn("vscode://file/owner/repo/src/main.py:42", first_call_args)
        self.assertIn("Fix this issue", first_call_args)
        
        # Check the second fallback comment content
        second_call_args = mock_pr.create_issue_comment.call_args_list[1][0][0]
        self.assertIn("tests/test.py", second_call_args)
        self.assertIn("**📍 Line:** `123`", second_call_args)
        self.assertIn("Add test case", second_call_args)


if __name__ == "__main__":
    unittest.main()

