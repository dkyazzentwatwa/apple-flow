# Contributing to Apple Flow

Thank you for your interest in contributing to Apple Flow! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Project Structure](#project-standards)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment. Be kind, constructive, and professional in all interactions.

## Getting Started

### Prerequisites

- macOS (required for Apple app integrations)
- Python 3.11+
- An AI CLI tool (Claude CLI or Codex CLI)
- Full Disk Access for your terminal (to read iMessage database)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/apple-flow.git
   cd apple-flow
   ```

## Development Setup

### 1. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -e ".[dev]"
```

If dev dependencies aren't configured, install manually:
```bash
pip install pytest ruff mypy
```

### 3. Set Up Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 4. Run Tests

```bash
pytest -q
```

All tests should pass before submitting a PR.

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-telegram-support`
- `fix/imessage-echo-loop`
- `docs/update-security-guide`
- `refactor/orchestrator-cleanup`

### Commit Messages

Follow conventional commits format:

```
type(scope): brief description

Optional longer description.

Fixes #issue-number
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(companion): add weekly review scheduling
fix(egress): prevent duplicate message sends
docs(security): add threat model documentation
```

### Code Style

- **Formatting**: Follow PEP 8 (use `ruff format`)
- **Imports**: Use absolute imports from `apple_flow`
- **Types**: Add type hints to new functions
- **Docstrings**: Use Google-style docstrings for public functions

```python
def handle_message(self, message: InboundMessage) -> OrchestrationResult:
    """Process an inbound message and return the result.
    
    Args:
        message: The inbound message to process.
        
    Returns:
        OrchestrationResult with kind, run_id, and response.
        
    Raises:
        ValueError: If the message is malformed.
    """
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_orchestrator.py

# Run specific test
pytest tests/test_orchestrator.py::test_handle_chat_message
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use descriptive test names:
  ```python
  def test_approval_sender_verification_blocks_different_sender():
      ...
  ```

### Test Coverage

We aim for high test coverage on critical paths:
- Security-related code (approval workflow, sender verification)
- Message handling (orchestrator)
- Apple integrations (ingress/egress)

## Pull Request Process

### Before Submitting

1. **Run tests**: `pytest -q` — all must pass
2. **Lint your code**: `ruff check src/`
3. **Type check**: `mypy src/apple_flow/`
4. **Update documentation** if needed
5. **Add tests** for new functionality

### PR Template

When you open a PR, include:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] New tests added for new functionality

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated (if applicable)
```

### Review Process

1. At least one approval required
2. All CI checks must pass
3. No merge conflicts
4. Squash and merge preferred

## Coding Standards

### Security Considerations

When contributing code that handles:
- **User input**: Sanitize and validate
- **File paths**: Check against `allowed_workspaces`
- **AppleScript**: Escape special characters
- **Approvals**: Verify sender identity

### Error Handling

- Use logging instead of print statements
- Catch specific exceptions, not bare `except:`
- Provide actionable error messages
- Never expose sensitive data in error messages

```python
# Good
try:
    result = subprocess.run(cmd, capture_output=True, timeout=30)
except subprocess.TimeoutExpired:
    logger.error("Command timed out after 30s: %s", cmd)
    return "Error: Request timed out."

# Bad
try:
    result = subprocess.run(cmd)
except:
    print("Something went wrong")
```

### Logging

Use the `logging` module with appropriate levels:

```python
logger = logging.getLogger("apple_flow.module_name")

logger.debug("Detailed diagnostic information")
logger.info("Normal operational messages")
logger.warning("Something unexpected but handled")
logger.error("Error that should be investigated")
logger.exception("Exception with full traceback")
```

## Project Structure

```
apple-flow/
├── src/apple_flow/          # Main source code
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── daemon.py            # Main event loop
│   ├── orchestrator.py      # Message handling
│   ├── config.py            # Configuration
│   ├── ingress.py           # iMessage input
│   ├── egress.py            # iMessage output
│   ├── mail_*.py            # Mail integration
│   ├── reminders_*.py       # Reminders integration
│   ├── notes_*.py           # Notes integration
│   ├── calendar_*.py        # Calendar integration
│   ├── companion.py         # Proactive assistant
│   ├── memory.py            # File-based memory
│   ├── policy.py            # Security policy engine
│   ├── store.py             # SQLite storage
│   └── apple_tools.py       # CLI tools
├── tests/                   # Test files
├── docs/                    # Documentation
├── scripts/                 # Setup/utility scripts
├── agent-office/            # Companion workspace
├── skills/                  # Codex skills
├── .env.example             # Configuration template
├── README.md                # Main documentation
├── SECURITY.md              # Security policy
├── CONTRIBUTING.md          # This file
└── pyproject.toml           # Package configuration
```

## Getting Help

- **Documentation**: Check `README.md` and `docs/`
- **Issues**: Search existing issues before opening a new one
- **Discussions**: Use GitHub Discussions for questions

## Recognition

Contributors are recognized in release notes. Thank you for helping make Apple Flow better!

---

**Questions?** Open a GitHub Discussion or issue and we'll help you get started.