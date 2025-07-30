#!/usr/bin/env python3
"""
Local test script for CI Rescue GitHub Action
This script simulates the GitHub Actions environment to test the action locally
"""

import os
import subprocess
import sys

def setup_test_environment():
    """Set up environment variables for local testing"""
    
    # Action inputs (these come from action.yml inputs)
    os.environ["INPUT_GITHUB_TOKEN"] = os.getenv("GH_TOKEN_MAX", "")
    os.environ["INPUT_OPENROUTER_API_KEY"] = os.getenv("OPENROUTER", "")
    os.environ["INPUT_MODEL"] = "openai/gpt-4o-mini"
    os.environ["INPUT_MAX_TOKENS"] = "1000"
    os.environ["INPUT_INCLUDE_LOGS"] = "true"
    os.environ["INPUT_COMMENT_MODE"] = "update-existing"
    
    # GitHub context variables (these are normally set by GitHub Actions)
    # You'll need to adjust these for your specific test case
    os.environ["GITHUB_REPOSITORY"] = "pbitkowski/ci-rescue-action"
    os.environ["GITHUB_SHA"] = "f8791dcff654e2bf36df2ff64630583e0c71de4c"
    os.environ["GITHUB_RUN_ID"] = "16603087193"  # From your debug script
    os.environ["GITHUB_EVENT_NAME"] = "pull_request"
    
    # Optional: Set up event payload for PR context
    # os.environ["GITHUB_EVENT_PATH"] = "/path/to/event.json"
    
    print("🔧 Environment setup complete!")
    print(f"   Repository: {os.environ['GITHUB_REPOSITORY']}")
    print(f"   Run ID: {os.environ['GITHUB_RUN_ID']}")
    print(f"   Model: {os.environ['INPUT_MODEL']}")
    print(f"   GitHub Token: {'✓' if os.environ['INPUT_GITHUB_TOKEN'] else '✗'}")
    print(f"   OpenRouter Key: {'✓' if os.environ['INPUT_OPENROUTER_API_KEY'] else '✗'}")

def run_action():
    """Run the action locally"""
    print("\n🚀 Running CI Rescue action...")
    
    # Check if virtual environment is activated
    if not os.environ.get('VIRTUAL_ENV'):
        print("⚠️  Warning: No virtual environment detected. Consider using 'source venv/bin/activate'")
    
    try:
        # Run the main action script
        result = subprocess.run([
            sys.executable, "src/main.py"
        ], capture_output=True, text=True)
        
        print("\n📋 Output:")
        print(result.stdout)
        
        if result.stderr:
            print("\n❌ Errors:")
            print(result.stderr)
        
        if result.returncode != 0:
            print(f"\n💥 Action failed with exit code: {result.returncode}")
            return False
        else:
            print("\n✅ Action completed successfully!")
            return True
            
    except Exception as e:
        print(f"\n❌ Failed to run action: {e}")
        return False

def validate_environment():
    """Validate that required environment variables are set"""
    required_vars = {
        "GH_TOKEN_MAX": "GitHub token for API access",
        "OPENROUTER": "OpenRouter API key for LLM access"
    }
    
    missing = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing.append(f"  - {var}: {description}")
    
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(var)
        print("\nMake sure to set these variables before running the test.")
        return False
    
    return True

def main():
    """Main test function"""
    print("🧪 CI Rescue Local Test")
    print("=" * 50)
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Setup test environment
    setup_test_environment()
    
    # Run the action
    success = run_action()
    
    if success:
        print("\n🎉 Test completed successfully!")
    else:
        print("\n💥 Test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
