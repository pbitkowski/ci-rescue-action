# CI Rescue - AI-Powered Failure Analysis

🚨 **Automatically analyze CI failures and get intelligent fix suggestions on your PRs!**

This GitHub Action uses AI to analyze your workflow failures and posts helpful comments on pull requests with specific suggestions on how to fix the issues.

## ✨ Features

- 🤖 **AI-Powered Analysis**: Uses OpenRouter (compatible with GPT-4, Claude, etc.) to analyze failures
- 📝 **Smart PR Comments**: Posts concise, actionable feedback directly on pull requests
- 🔄 **Update Mode**: Updates existing comments instead of spamming new ones
- 📊 **Multi-Failure Support**: Handles multiple job failures in a single run
- 🛡️ **Secure**: Uses your existing GitHub token, only needs OpenRouter API key

## 🚀 Quick Start

### 1. Add to your workflow

Create or update `.github/workflows/your-workflow.yml`:

```yaml
name: CI Pipeline
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          # Your existing CI steps here
          npm test
  
  # Add this job to handle failures
  ci-rescue:
    if: failure()  # Only run when previous jobs fail
    needs: [test]  # List all your job names here
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      actions: read
    steps:
      - name: AI Failure Analysis
        uses: yourusername/ci-rescue-action@v1
        with:
          openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
          # github-token is automatically provided
```

### 2. Add OpenRouter API Key

1. Get an API key from [OpenRouter](https://openrouter.ai/)
2. Add it to your repository secrets as `OPENROUTER_API_KEY`

### 3. That's it! 🎉

Now when your CI fails, you'll get intelligent comments like:

> 🚨 **CI Failure Analysis**
> 
> The test job failed because of a missing dependency. The error indicates that the module `@testing-library/jest-dom` cannot be found.
> 
> **Fix Steps:**
> 1. Install the missing dependency: `npm install --save-dev @testing-library/jest-dom`
> 2. Make sure it's imported in your test setup file
> 3. Re-run the tests
> 
> **Suggested Code Change:**
> ```bash
> npm install --save-dev @testing-library/jest-dom
> ```

## ⚙️ Configuration

### Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `github-token` | GitHub token for API access | ✅ | `${{ github.token }}` |
| `openrouter-api-key` | OpenRouter API key | ✅ | - |
| `model` | OpenRouter model to use | ❌ | `openai/gpt-4o-mini` |
| `max-tokens` | Maximum tokens for LLM response | ❌ | `1000` |
| `include-logs` | Include job logs in analysis | ❌ | `true` |
| `comment-mode` | Comment handling mode | ❌ | `update-existing` |

### Comment Modes

- `update-existing`: Updates the same comment (recommended)
- `create-new`: Always creates new comments
- `replace`: Replaces existing comments entirely

### Supported Models

Any OpenRouter-compatible model:
- `openai/gpt-4o-mini` (recommended, cost-effective)
- `openai/gpt-4o`
- `anthropic/claude-3.5-sonnet`
- `google/gemini-pro`
- And many more!

## 🏗️ Advanced Usage

### Multiple Job Dependencies

```yaml
ci-rescue:
  if: failure()
  needs: [test, lint, build, deploy]  # All your jobs
  runs-on: ubuntu-latest
  # ... rest of config
```

### Custom Model Configuration

```yaml
- name: AI Failure Analysis
  uses: yourusername/ci-rescue-action@v1
  with:
    openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
    model: "anthropic/claude-3.5-sonnet"
    max-tokens: 1500
    comment-mode: "create-new"
```

### Conditional Execution

```yaml
ci-rescue:
  if: failure() && github.event_name == 'pull_request'
  # Only run on PR failures, not pushes to main
```

## 🔒 Security & Permissions

This action requires minimal permissions:
- `contents: read` - To access repository content
- `pull-requests: write` - To post comments on PRs  
- `actions: read` - To read workflow run information

The action only uses:
- Your GitHub token (automatically provided)
- OpenRouter API key (stored in secrets)

## 🤝 Contributing

Contributions welcome! Please read the contributing guidelines and submit PRs.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🆘 Support

- 📚 [Documentation](https://github.com/yourusername/ci-rescue-action/wiki)
- 🐛 [Report Issues](https://github.com/yourusername/ci-rescue-action/issues)
- 💬 [Discussions](https://github.com/yourusername/ci-rescue-action/discussions)
