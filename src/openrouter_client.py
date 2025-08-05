#!/usr/bin/env python3
"""
OpenRouter Client for analyzing CI failures
"""

import requests
from models import FailureInfo
from constants import CI_FAILURE_ANALYSIS_MAIN_TITLE

class OpenRouterClient:
    """Client for interacting with OpenRouter API"""

    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"

    def analyze_failure(self, failure_info: FailureInfo, max_tokens: int = 1000) -> str:
        """Analyze CI failure and provide suggestions"""
        print(f"🔍 Failure info: {failure_info}")
        error_context = self._extract_error_context(failure_info.logs)
        print(f"🔍 Analyzing failure in job '{failure_info.logs}'...")

        prompt = self._create_prompt(failure_info, error_context)
        headers = self._create_headers()
        data = self._create_data(prompt, max_tokens)

        return self._post_analysis_request(headers, data)

    def _create_prompt(self, failure_info: FailureInfo, error_context: str) -> str:
        """Create prompt for the AI model"""
        return f"""
You are an expert CI/CD assistant. Analyze this GitHub Actions workflow failure and provide a concise, actionable comment for the pull request.

- Job: {failure_info.job_name}
- Step: {failure_info.step_name}
- Status: {failure_info.conclusion}

**Error Details:**
{error_context}

**Recent Log Output:**
```
{failure_info.logs[-1500:]}
```

Please provide:
1. **Root Cause**: Identify the specific error
2. **Solution**: Provide clear, actionable steps to fix the issue
3. **Code Fix**: If applicable, suggest specific code changes or commands

Be specific about:
- File names and line numbers if mentioned in logs.
- Exact error messages and their meaning
- Command-line fixes when possible

Format as a helpful GitHub comment in markdown. Start with "{CI_FAILURE_ANALYSIS_MAIN_TITLE}".

If the failure is related to specific files, provide annotations in a JSON block:
<<<CI-RESCUE-ANNOTATIONS>>>
{{
  "annotations": [
    {{
      "path": "path/to/offending_file.py",
      "start_line": 42,
      "end_line": 42,
      "annotation_level": "failure",
      "message": "A brief explanation of why this line is causing a failure."
    }}
  ]
}}
<<<CI-RESCUE-ANNOTATIONS>>>
"""

    def _create_headers(self) -> dict:
        """Create headers for the HTTP request"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ci-rescue-action",
            "X-Title": "CI Rescue Action"
        }

    def _create_data(self, prompt: str, max_tokens: int) -> dict:
        """Create data payload for the HTTP request"""
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.1
        }

    def _post_analysis_request(self, headers: dict, data: dict) -> str:
        """Post the analysis request to the AI model"""
        try:
            response = requests.post(
                url=f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"{CI_FAILURE_ANALYSIS_MAIN_TITLE}\n\n❌ Failed to analyze the error with AI: {str(e)}\n\n**Manual Review Needed:**\nPlease check the logs for more details."

    def _extract_error_context(self, logs: str) -> str:
        """Extract key error information from logs with surrounding context"""
        if not logs:
            return "No logs available"

        error_indicators = [
            "ERROR", "FAILED", "Error:", "error:", "Exception:", "Traceback",
            "TabError:", "SyntaxError:", "ImportError:", "ModuleNotFoundError:",
            "AssertionError:", "##[error]", "FAIL:", "FAILURE:", "Remove unused import:"
        ]

        lines = logs.split('\n')
        error_line_indices = []

        # Find all lines with error indicators (case-insensitive)
        for i, line in enumerate(lines):
            if any(indicator.lower() in line.lower() for indicator in error_indicators):
                error_line_indices.append(i)

        if not error_line_indices:
            # Fallback to last few lines of logs
            return "\n".join([line.strip() for line in lines[-10:] if line.strip()])

        # Create separate context blocks for each error (5 lines before and after)
        context_blocks = []
        
        for error_idx in error_line_indices:
            start = max(0, error_idx - 5)
            end = min(len(lines), error_idx + 6)  # +6 because range is exclusive
            
            # Extract context for this specific error
            block_lines = []
            for i in range(start, end):
                if i < len(lines):
                    prefix = ">>> " if i == error_idx else "    "  # Highlight error line
                    block_lines.append(f"{prefix}{lines[i].rstrip()}")
            
            if block_lines:
                # Parse traceback for real file:line info, fallback to log line
                file_line_info = self._parse_traceback_for_file_line(lines, error_idx)
                if file_line_info:
                    header = f"[Error Context #{len(context_blocks) + 1} - {file_line_info}]"
                else:
                    header = f"[Error Context #{len(context_blocks) + 1} - Log Line {error_idx + 1}]"
                
                context_block = f"{header}\n" + "\n".join(block_lines)
                context_blocks.append(context_block)
        
        print(f"🔍 Found {len(context_blocks)} separate error contexts")
        
        # Limit output to avoid overwhelming the AI (max 5 error contexts)
        if len(context_blocks) > 5:
            context_blocks = context_blocks[-5:]  # Take the last 5 error contexts
            print(f"🔍 Limited to {len(context_blocks)} most recent error contexts")

        return "\n\n" + "="*50 + "\n\n".join([""] + context_blocks) + "\n\n" + "="*50

    def _parse_traceback_for_file_line(self, lines, error_idx: int):
        """Parse traceback information to find real file:line references"""
        import re
        
        # Look in surrounding lines for traceback patterns
        search_start = max(0, error_idx - 10)
        search_end = min(len(lines), error_idx + 10)
        
        # Common traceback patterns:
        patterns = [
            r'File "([^"]+)", line (\d+),',  # Python traceback: File "test.py", line 46,
            r'([^:\s]+):(\d+): (\w+Error)',  # pytest style: tests/test_file.py:46: AssertionError
            r'([^:\s]+\.py):(\d+)',          # Generic: file.py:123
            r'at ([^:]+):(\d+):(\d+)',       # JavaScript style: at file.js:46:12
        ]
        
        for i in range(search_start, search_end):
            if i < len(lines):
                line = lines[i]
                for pattern in patterns:
                    match = re.search(pattern, line)
                    if match:
                        if len(match.groups()) >= 2:
                            file_path = match.group(1)
                            line_num = match.group(2)
                            # Clean up file path (remove full paths, keep relative)
                            if '/' in file_path:
                                file_path = '/'.join(file_path.split('/')[-2:])  # Keep last 2 parts
                            return f"File {file_path}:{line_num}"
        
        return None
