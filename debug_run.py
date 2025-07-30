#!/usr/bin/env python3
"""
Quick script to analyze GitHub Actions run failure
"""

import os
import requests
import json

# GitHub API configuration
GITHUB_TOKEN = os.getenv('GH_TOKEN_MAX')
RUN_ID = '16603415771'
REPO = 'pbitkowski/ci-rescue-action'

def get_run_details():
    """Get workflow run details"""
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Get run details
    url = f'https://api.github.com/repos/{REPO}/actions/runs/{RUN_ID}'
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error getting run details: {response.status_code}")
        print(response.text)
        return
    
    run_data = response.json()
    print(f"🔍 Workflow Run: {run_data['name']}")
    print(f"📅 Created: {run_data['created_at']}")
    print(f"📊 Status: {run_data['status']} / {run_data['conclusion']}")
    print(f"🌿 Branch: {run_data['head_branch']}")
    print(f"💬 Commit: {run_data['head_commit']['message']}")
    print("\n" + "="*60 + "\n")
    
    # Get jobs for this run
    jobs_url = f'https://api.github.com/repos/{REPO}/actions/runs/{RUN_ID}/jobs'
    jobs_response = requests.get(jobs_url, headers=headers)
    
    if jobs_response.status_code != 200:
        print(f"Error getting jobs: {jobs_response.status_code}")
        return
    
    jobs_data = jobs_response.json()
    
    for job in jobs_data['jobs']:
        print(f"🔧 Job: {job['name']}")
        print(f"   Status: {job['status']} / {job['conclusion']}")
        print(f"   Started: {job['started_at']}")
        
        if job['conclusion'] in ['failure', 'cancelled']:
            print(f"   ❌ FAILED")
            
            # Get job logs
            logs_url = f"https://api.github.com/repos/{REPO}/actions/jobs/{job['id']}/logs"
            logs_response = requests.get(logs_url, headers=headers)
            
            if logs_response.status_code == 200:
                logs = logs_response.text
                print(f"   📋 Logs (last 1000 chars):")
                print("   " + "-" * 50)
                # Show last part of logs where errors usually are
                log_lines = logs.split('\n')[-20:]  # Last 20 lines
                for line in log_lines:
                    if line.strip():
                        print(f"   {line}")
                print("   " + "-" * 50)
            
            # Show failed steps
            print(f"   🔍 Steps:")
            for step in job.get('steps', []):
                status_icon = "✅" if step['conclusion'] == 'success' else "❌" if step['conclusion'] == 'failure' else "⏸️"
                print(f"     {status_icon} {step['name']} ({step.get('conclusion', 'unknown')})")
                
                if step['conclusion'] == 'failure':
                    print(f"       💥 Failed at step: {step['name']}")
        
        print("\n" + "-" * 40 + "\n")

if __name__ == '__main__':
    if not GITHUB_TOKEN:
        print("❌ GH_TOKEN_MAX environment variable not set")
        exit(1)
    
    get_run_details()
