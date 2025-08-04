#!/usr/bin/env python3
"""
GitHub client utilities
"""

import os
import json
from typing import List, Optional
from github import Github
from github.PullRequest import PullRequest
import requests
from models import FailureInfo

class GitHubClient:
    def __init__(self, github_token: str, repository: str, run_id: str):
        self.github_token = github_token
        self.repository = repository
        self.run_id = run_id
        self.github = Github(self.github_token)

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

            prs = repo.get_pulls(state="open")
            for pr in prs:
                if pr.head.sha == os.getenv("GITHUB_SHA"):
                    return pr

            return None

        except Exception as e:
            print(f"Error getting pull request: {e}")
            return None
