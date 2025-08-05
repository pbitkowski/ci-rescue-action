#!/usr/bin/env python3
"""
CI Rescue - AI-Powered GitHub Action for CI Failure Analysis
"""

import os
import sys
import json
from typing import List, Optional
from github_client import GitHubClient
from openrouter_client import OpenRouterClient
from models import FailureInfo
from constants import CI_ANNOTATION_MARKER


class CIRescue:
    """Main class for CI Rescue functionality"""

    def __init__(self):
        self.github_token = os.getenv("INPUT_GITHUB_TOKEN")
        self.openrouter_api_key = os.getenv("INPUT_OPENROUTER_API_KEY")
        self.model = os.getenv("INPUT_MODEL", "openai/gpt-4o-mini")
        self.max_tokens = int(os.getenv("INPUT_MAX_TOKENS", "1000"))
        
        # Job filtering - only analyze test and lint failures
        self.job_filter = ["test", "lint"]

        # GitHub context
        self.repository = os.getenv("GITHUB_REPOSITORY")
        self.run_id = os.getenv("GITHUB_RUN_ID")

        # Initialize clients
        self.github = GitHubClient(self.github_token, self.repository, self.run_id)
        self.openrouter = OpenRouterClient(self.openrouter_api_key, self.model)

        if not all([self.github_token, self.openrouter_api_key, self.repository, self.run_id]):
            raise ValueError("Missing required environment variables")

    def run(self) -> None:
        """Main execution method"""
        print("🔍 CI Rescue starting analysis...")
        
        print("🎯 Analyzing test and lint failures only")

        failures = self.github.get_workflow_run_failures()
        if not failures:
            print("✅ No failures detected in this workflow run")
            return

        print(f"🚨 Found {len(failures)} total failure(s)")
        
        # Apply job filtering for test and lint only
        original_count = len(failures)
        failures = self._filter_failures_by_job_type(failures)
        if len(failures) != original_count:
            print(f"🔽 Filtered to {len(failures)} test/lint failure(s) from {original_count} total failures")
        
        if not failures:
            print("✅ No test or lint failures found")
            return

        pr = self.github.get_pull_request()
        if not pr:
            print("ℹ️  No pull request found for this run - skipping comment")
            return

        print(f"📝 Found PR #{pr.number}: {pr.title}")

        # Analyze each failure individually
        all_analysis_parts = []
        all_annotations = []
        
        for i, failure in enumerate(failures, 1):
            print(f"🤖 Analyzing failure {i}/{len(failures)} in job '{failure.job_name}'...")
            
            analysis_text = self.openrouter.analyze_failure(failure, self.max_tokens)
            comment_part, annotations = self._parse_analysis_with_annotations(analysis_text)
            
            # Add job header to each analysis
            job_header = f"\n\n## 🚨 **Job: {failure.job_name}** (Step: {failure.step_name})\n\n"
            full_analysis = job_header + comment_part
            all_analysis_parts.append(full_analysis)
            
            if annotations:
                print(f"📌 Found {len(annotations)} annotations for job '{failure.job_name}'")
                all_annotations.extend(annotations)
            else:
                print(f"ℹ️  No annotations found for job '{failure.job_name}'")
        
        # Combine all analyses into a comprehensive comment
        main_comment = f"# 🔧 **CI Rescue Analysis** - {len(failures)} Test/Lint Failure(s)\n"
        main_comment += "".join(all_analysis_parts)
        
        # Add annotations summary if we have any
        if all_annotations:
            print(f"📌 Adding {len(all_annotations)} total annotations to PR comment summary")
            annotation_comments = self.format_annotations_for_comment(all_annotations)
            main_comment += annotation_comments
        else:
            print("ℹ️  No annotations to add to PR comment")

        print("💬 Posting comprehensive PR comment...")
        self.github.post_or_update_comment(pr, main_comment)
        
        if all_annotations:
            print(f"📍 Processing {len(all_annotations)} annotations for line-level comments...")
            review_comments = self.convert_annotations_to_review_comments(all_annotations)
            print(f"✅ Converted {len(review_comments)} valid annotations to review comments")
            self.github.post_line_annotations(pr, review_comments)
        else:
            print("📝 No annotations to process for line-level comments")

        print("✅ Analysis complete!")

    def _filter_failures_by_job_type(self, failures: List[FailureInfo]) -> List[FailureInfo]:
        """Filter failures to only include test and lint job types"""
        filtered_failures = []
        
        for failure in failures:
            job_name_lower = failure.job_name.lower()
            
            # Check if job name contains test or lint
            if "test" in job_name_lower or "lint" in job_name_lower:
                print(f"✅ Including job: {failure.job_name}")
                filtered_failures.append(failure)
            else:
                print(f"⏭️  Skipping job: {failure.job_name} (not test/lint)")
        
        return filtered_failures

    def _parse_analysis_with_annotations(self, analysis_text: str) -> (str, Optional[List[dict]]):
        """Parse the AI response to separate the comment from annotations."""
        marker = "<<<CI-RESCUE-ANNOTATIONS>>>"
        print(f"🔍 Parsing AI response for annotations (length: {len(analysis_text)} chars)...")

        if marker in analysis_text:
            print("📍 Found annotation marker in AI response")
            parts = analysis_text.split(marker)
            comment = parts[0]

            try:
                annotations_json_str = parts[1]
                print(f"📋 Raw annotation JSON: {annotations_json_str[:200]}..." if len(annotations_json_str) > 200 else f"📋 Raw annotation JSON: {annotations_json_str}")

                annotations_data = json.loads(annotations_json_str)
                annotations = annotations_data.get("annotations")

                if annotations:
                    print(f"✅ Successfully parsed {len(annotations)} annotation(s)")
                    for i, annotation in enumerate(annotations):
                        print(f"   📌 Annotation {i+1}: {annotation.get('path', 'unknown')}:{annotation.get('start_line', 'unknown')} - {annotation.get('message', 'no message')[:50]}...")
                else:
                    print("⚠️  No annotations found in parsed JSON")

                return comment.strip(), annotations

            except (json.JSONDecodeError, IndexError, AttributeError) as e:
                print(f"❌ Failed to parse annotation JSON: {e}")
                print(f"   Raw content: {parts[1][:100] if len(parts) > 1 else 'no content'}...")
                return analysis_text.replace(marker, ""), None
        else:
            print("ℹ️  No annotation markers found in AI response")

        return analysis_text, None

    def convert_annotations_to_review_comments(self, annotations):
        """Convert AI annotations to GitHub ReviewComment format"""
        review_comments = []
        
        for annotation in annotations:
            path = annotation.get('path', '')
            if not path:
                print(f"⚠️  Skipping annotation without path: {annotation}")
                continue
                
            try:
                line = int(annotation.get('start_line', annotation.get('line', 1)))
            except (ValueError, TypeError):
                print(f"⚠️  Invalid line number in annotation: {annotation}")
                continue
                
            message = annotation.get('message', 'No message provided')
            level = annotation.get('annotation_level', 'notice')
            
            # Create emoji based on level  
            level_emoji = {
                'failure': '❌',
                'error': '🚨', 
                'warning': '⚠️',
                'notice': 'ℹ️'
            }.get(level, '📝')
            
            review_comment = {
                'path': path,
                'line': line,
                'body': f"{level_emoji} **{CI_ANNOTATION_MARKER}**\n\n{message}"
            }
            
            review_comments.append(review_comment)
            
        print(f"🔍 Converted {len(annotations)} annotations to {len(review_comments)} review comments")
        return review_comments

    def format_annotations_for_comment(self, annotations: List[dict]) -> str:
        """Format annotations as markdown for inclusion in PR comment."""
        if not annotations:
            return ""

        print(f"📝 Formatting {len(annotations)} annotations for PR comment")

        formatted = "\n\n## 📍 **Code Annotations**\n\n"

        for annotation in annotations:
            path = annotation.get('path', 'unknown file')
            start_line = annotation.get('start_line', annotation.get('line', 'unknown'))
            end_line = annotation.get('end_line', start_line)
            message = annotation.get('message', 'No message provided')
            level = annotation.get('annotation_level', 'notice')

            # Choose emoji based on annotation level
            level_emoji = {
                'failure': '❌',
                'error': '🚨', 
                'warning': '⚠️',
                'notice': 'ℹ️'
            }.get(level, '📝')

            if start_line == end_line:
                line_info = f"Line {start_line}"
            else:
                line_info = f"Lines {start_line}-{end_line}"

            formatted += f"{level_emoji} **{path}** ({line_info})\n"
            formatted += f"   {message}\n\n"

        return formatted

    def _create_failure_summary(self, failures: List[FailureInfo]) -> str:
        """Create summary for additional failures"""
        other_failures = "\n".join([
            f"- **{f.job_name}** → {f.step_name} ({f.conclusion})"
            for f in failures[1:]
        ])
        return f"\n\n**Additional Failures:**\n{other_failures}"


def main():
    """Entry point for CI Rescue"""
    try:
        rescue = CIRescue()
        rescue.run()
    except Exception as e:
        print(f"❌ CI Rescue failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
