#!/usr/bin/env python3
"""
GitHub client utilities
"""

import json
import os

from typing import List, Optional
from github import Github
from github.PullRequest import PullRequest
import requests
from models import FailureInfo
from constants import CI_ANNOTATION_MARKER, CI_RESCUE_COMMENT_MARKER


class GitHubClient:
    def __init__(self, github_token: str, repository: str, run_id: str):
        self.github_token = github_token
        self.repository = repository
        self.run_id = run_id
        self.github = Github(self.github_token)
        self.event_name = os.getenv("GITHUB_EVENT_NAME")
        self.sha = os.getenv("GITHUB_SHA")
        self.comment_mode = os.getenv("INPUT_COMMENT_MODE", "update-existing")

    def get_workflow_run_failures(self) -> List[FailureInfo]:
        """Get failure information from the current workflow run"""
        failures = []

        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        jobs_url = f"https://api.github.com/repos/{self.repository}/actions/runs/{self.run_id}/jobs"
        response = requests.get(jobs_url, headers=headers)

        if response.status_code != 200:
            print(f"Error getting jobs: {response.status_code}")
            return failures

        jobs_data = response.json()
        jobs = jobs_data.get('jobs', [])
        
        for job in jobs:
            if job.get('conclusion') in ["failure", "cancelled", "timed_out"]:
                error_steps = [step for step in job.get('steps', []) if step.get('conclusion') == "failure"]

                for step in error_steps:
                    logs = self.get_job_logs(job['id'])

                    failures.append(FailureInfo(
                        job_name=job.get('name', 'Unknown Job'),
                        step_name=step.get('name', 'Unknown Step'),
                        error_message=step.get('conclusion', 'Unknown error'),
                        logs=logs,
                        conclusion=job.get('conclusion', 'Unknown')
                    ))
        
        return failures

    def get_job_logs(self, job_id: int) -> str:
        """Get logs for a specific job"""
        try:
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }

            url = f"https://api.github.com/repos/{self.repository}/actions/jobs/{job_id}/logs"
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                logs = response.text
                return logs[-5000:] if len(logs) > 5000 else logs
            else:
                return f"Could not retrieve logs (status: {response.status_code})"

        except Exception as e:
            return f"Error retrieving logs: {str(e)}"

    def get_pull_request(self) -> Optional[PullRequest]:
        """Get the pull request associated with this run"""
        try:
            repo = self.github.get_repo(self.repository)
            
            # For pull_request events, get PR from event
            if self.event_name == "pull_request":
                event_path = os.getenv("GITHUB_EVENT_PATH")
                if event_path and os.path.exists(event_path):
                    with open(event_path, 'r') as f:
                        event_data = json.load(f)
                    pr_number = event_data.get("pull_request", {}).get("number")
                    if pr_number:
                        return repo.get_pull(pr_number)
            
            # For other events, search for PRs with this commit
            prs = repo.get_pulls(state="open")
            for pr in prs:
                if pr.head.sha == self.sha:
                    return pr
                    
            return None
            
        except Exception as e:
            print(f"Error getting pull request: {e}")
            return None

    def post_or_update_comment(self, pr: PullRequest, analysis: str) -> None:
        """Post or update a comment on the pull request"""
        comment_body = f"{CI_RESCUE_COMMENT_MARKER}\n{analysis}"
        
        try:
            if self.comment_mode == "update-existing":
                # Look for existing comment
                comments = pr.get_issue_comments()
                for comment in comments:
                    if CI_RESCUE_COMMENT_MARKER in comment.body:
                        comment.edit(comment_body)
                        print(f"Updated existing comment on PR #{pr.number}")
                        return
            
            # Create new comment if no existing one found or mode is create-new
            pr.create_issue_comment(comment_body)
            print(f"Created new comment on PR #{pr.number}")
            
        except Exception as e:
            print(f"Error posting comment: {e}")

    def remove_previous_ci_rescue_annotations(self, pr):
        """Remove previous CI Rescue annotation comments to avoid duplicates"""
        try:
            print("🧹 Cleaning up previous CI Rescue annotations...")
            
            # Get all review comments on the PR
            review_comments = pr.get_review_comments()
            ci_rescue_comments = []
            
            for comment in review_comments:
                # Check if this is a CI Rescue annotation comment
                if comment.body and CI_ANNOTATION_MARKER in comment.body:
                    ci_rescue_comments.append(comment)
            
            if ci_rescue_comments:
                print(f"🗑️  Found {len(ci_rescue_comments)} previous CI Rescue annotations to remove")
                
                # Delete each CI Rescue annotation comment
                for comment in ci_rescue_comments:
                    try:
                        comment.delete()
                        print(f"   ✅ Deleted annotation on {comment.path}:{comment.line if hasattr(comment, 'line') else 'unknown'}")
                    except Exception as e:
                        print(f"   ⚠️  Failed to delete annotation: {e}")
                        
                print(f"✅ Cleaned up {len(ci_rescue_comments)} previous annotations")
            else:
                print("ℹ️  No previous CI Rescue annotations found")
                
        except Exception as e:
            print(f"⚠️  Error cleaning up previous annotations: {e}")

    def post_line_annotations(self, pr, review_comments):
        """Post line annotations on the pull request"""
        if not review_comments:
            return
            
        # Clean up previous CI Rescue annotations first
        self.remove_previous_ci_rescue_annotations(pr)
        
        # Validate comment structure
        for i, comment in enumerate(review_comments):
            if not isinstance(comment, dict):
                raise ValueError(f"Review comment {i} must be a dict")
            if 'path' not in comment or 'line' not in comment or 'body' not in comment:
                raise ValueError(f"Review comment {i} missing required fields: path, line, body")
            if not isinstance(comment['line'], int):
                raise ValueError(f"Review comment {i} 'line' must be an integer")
        
        # Create a review with the comments
        try:
            review = pr.create_review(
                commit=pr.get_commits().reversed[0],  # Latest commit
                event='COMMENT',
                comments=review_comments
            )
            print(f"✅ Posted {len(review_comments)} line annotations as review #{review.id}")
            
        except Exception as e:
            print(f"❌ Failed to create review with line comments: {e}")
            print("🔄 Falling back to individual comments...")
            
            # Fallback: Post individual comments
            for comment_data in review_comments:
                try:
                    pr.create_review_comment(
                        body=comment_data['body'],
                        commit=pr.get_commits().reversed[0],
                        path=comment_data['path'],
                        line=comment_data['line']
                    )
                    print(f"   ✅ Posted comment on {comment_data['path']}:{comment_data['line']}")
                except Exception as comment_error:
                    print(f"   ❌ Failed to post comment on {comment_data['path']}:{comment_data['line']}: {comment_error}")
