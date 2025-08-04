#!/usr/bin/env python3
"""
Data models for CI Rescue
"""

from dataclasses import dataclass


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
