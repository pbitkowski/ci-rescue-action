#!/usr/bin/env python3
"""
CI Rescue - AI-Powered GitHub Action for CI Failure Analysis
"""

import os
import sys
import json
from typing import List, Optional
from dataclasses import dataclass
from github import Github
from github.PullRequest import PullRequest
import requests


@dataclass
class FailureInfo:
    """Container for CI failure information"""
    job_name: str
    step_name: str
    error_message: str
    logs: str
    conclusion: str
    full_logs: str = ""  # Full logs for better context
    error_details: str = ""  # Extracted specific error details


class OpenRouterClient:
    """Client for interacting with OpenRouter API"""
    
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"
    
    def analyze_failure(self, failure_info: FailureInfo, max_tokens: int = 1000) -> str:
        """Analyze CI failure and provide suggestions"""
        
        # Extract specific error details from logs
        error_context = self._extract_error_context(failure_info.logs)
        
        prompt = f"""You are an expert CI/CD assistant. Analyze this GitHub Actions workflow failure and provide a concise, actionable comment for the pull request.

**Failure Context:**
- Job: {failure_info.job_name}
- Step: {failure_info.step_name}
- Status: {failure_info.conclusion}

**Error Details:**
{error_context}

**Recent Log Output:**
```
{failure_info.logs[-1500:]}  # Show recent logs
```

Please provide:
1. **Root Cause**: Identify the specific error (e.g., syntax error, missing dependency, test failure, linting issue)
2. **Solution**: Provide clear, actionable steps to fix the issue
3. **Code Fix**: If applicable, suggest specific code changes or commands

Be specific about:
- File names and line numbers if mentioned in logs
- Exact error messages and their meaning
- Command-line fixes when possible

Format as a helpful GitHub comment in markdown. Start with "🚨 **CI Failure Analysis**"."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ci-rescue-action",
            "X-Title": "CI Rescue Action"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            return f"🚨 **CI Failure Analysis**\n\n❌ Failed to analyze the error with AI: {str(e)}\n\n**Manual Review Needed:**\nJob `{failure_info.job_name}` failed at step `{failure_info.step_name}` with status `{failure_info.conclusion}`.\n\nPlease check the logs for more details."
        
    def _extract_error_context(self, logs: str) -> str:
        """Extract key error information from logs"""
        if not logs:
            return "No logs available"
        
        error_indicators = [
            "ERROR", "FAILED", "Error:", "error:", "Exception:", "Traceback",
            "TabError:", "SyntaxError:", "ImportError:", "ModuleNotFoundError:",
            "AssertionError:", "##[error]", "FAIL:", "FAILURE:", "Remove unused import:"
        ]
        
        lines = logs.split('\n')
        error_lines = []
        
        for line in lines:
            if any(indicator in line for indicator in error_indicators):
                error_lines.append(line.strip())
        
        if error_lines:
            return "\n".join(error_lines[-5:])  # Last 5 error lines
        else:
            # Fallback to last few lines of logs
            return "\n".join([line.strip() for line in lines[-10:] if line.strip()])


class CIRescue:
    """Main class for CI Rescue functionality"""
    
    def __init__(self):
        self.github_token = os.getenv("INPUT_GITHUB_TOKEN")
        self.openrouter_api_key = os.getenv("INPUT_OPENROUTER_API_KEY")
        self.model = os.getenv("INPUT_MODEL", "openai/gpt-4o-mini")
        self.max_tokens = int(os.getenv("INPUT_MAX_TOKENS", "1000"))
        self.include_logs = os.getenv("INPUT_INCLUDE_LOGS", "true").lower() == "true"
        self.comment_mode = os.getenv("INPUT_COMMENT_MODE", "update-existing")
        
        # GitHub context
        self.repository = os.getenv("GITHUB_REPOSITORY")
        self.sha = os.getenv("GITHUB_SHA")
        self.run_id = os.getenv("GITHUB_RUN_ID")
        self.event_name = os.getenv("GITHUB_EVENT_NAME")
        
        # Initialize clients
        self.github = Github(self.github_token)
        self.openrouter = OpenRouterClient(self.openrouter_api_key, self.model)
        
        if not all([self.github_token, self.openrouter_api_key, self.repository, self.run_id]):
            raise ValueError("Missing required environment variables")
    
    def get_workflow_run_failures(self) -> List[FailureInfo]:
        """Get failure information from the current workflow run"""
        failures = []
        
        # Use GitHub REST API directly to get jobs
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
                # Extract error information from job steps
                error_steps = [step for step in job.get('steps', []) if step.get('conclusion') == "failure"]
                
                for step in error_steps:
                    logs = ""
                    if self.include_logs:
                        logs = self._get_job_logs(job['id'])
                    
                    failures.append(FailureInfo(
                        job_name=job.get('name', 'Unknown Job'),
                        step_name=step.get('name', 'Unknown Step'),
                        error_message=step.get('conclusion', 'Unknown error'),
                        logs=logs,
                        conclusion=job.get('conclusion', 'Unknown')
                    ))
        
        return failures
    
    def _get_job_logs(self, job_id: int) -> str:
        """Get logs for a specific job"""
        try:
            # Use GitHub API to get job logs
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            url = f"https://api.github.com/repos/{self.repository}/actions/jobs/{job_id}/logs"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                # Return last 2000 characters of logs for better context
                logs = response.text
                return logs[-2000:] if len(logs) > 2000 else logs
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
        comment_marker = "<!-- CI-RESCUE-COMMENT -->"
        comment_body = f"{comment_marker}\n{analysis}"
        
        try:
            if self.comment_mode == "update-existing":
                # Look for existing comment
                comments = pr.get_issue_comments()
                for comment in comments:
                    if comment_marker in comment.body:
                        comment.edit(comment_body)
                        print(f"Updated existing comment on PR #{pr.number}")
                        return
            
            # Create new comment if no existing one found or mode is create-new
            pr.create_issue_comment(comment_body)
            print(f"Created new comment on PR #{pr.number}")
            
        except Exception as e:
            print(f"Error posting comment: {e}")
    
    def run(self) -> None:
        """Main execution method"""
        print("🔍 CI Rescue starting analysis...")
        
        # Get failure information
        failures = self.get_workflow_run_failures()
        
        if not failures:
            print("✅ No failures detected in this workflow run")
            return
        
        print(f"🚨 Found {len(failures)} failure(s)")
        
        # Get associated pull request
        pr = self.get_pull_request()
        if not pr:
            print("ℹ️  No pull request found for this run - skipping comment")
            return
        
        print(f"📝 Found PR #{pr.number}: {pr.title}")
        
        # Analyze the most critical failure (first one)
        primary_failure = failures[0]
        print(f"🤖 Analyzing failure in job '{primary_failure.job_name}'...")
        
        analysis = self.openrouter.analyze_failure(
            primary_failure, self.max_tokens
        )

        # Add summary if multiple failures
        if len(failures) > 1:
            other_failures = "\n".join([
                f"- **{f.job_name}** → {f.step_name} ({f.conclusion})"
                for f in failures[1:]
            ])
            analysis += f"\n\n**Additional Failures:**\n{other_failures}"

        # Post comment to PR
        self.post_or_update_comment(pr, analysis)
        print("✅ Analysis complete!")


def main():
    """Entry point"""
    try:
        rescue = CIRescue()
        rescue.run()
    except Exception as e:
        print(f"❌ CI Rescue failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
