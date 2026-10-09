# Contributing to deepDDW

Thank you for your interest in contributing to deepDDW! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md) in all interactions with the project.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a new branch for your feature or bug fix
5. Make your changes and commit them
6. Push to your fork and submit a pull request

## Development Setup

### Prerequisites

- Python 3.11 or higher
- pip or uv (for dependency management)
- Git

### Local Development

```bash
# Clone the repository
git clone https://github.com/your-username/deepddw.git
cd deepddw

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the development server
python -m uvicorn core.main:app --reload --host 0.0.0.0 --port 8500
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov-report=term-missing

# Run specific test file
pytest tests/test_memory_layered.py
```

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates.

When creating a bug report, include:

1. A clear and descriptive title
2. Steps to reproduce the issue
3. Expected behavior
4. Actual behavior
5. Environment details (OS, Python version, etc.)
6. Any error messages or logs

### Suggesting Features

Feature suggestions are welcome! Please:

1. Check if the feature already exists or is planned
2. Provide a clear description of the feature
3. Explain why it would be useful
4. Include any relevant use cases

### Contributing Code

1. Find an issue to work on or create one
2. Comment on the issue to let others know you're working on it
3. Create a feature branch from `main`
4. Make your changes following our coding standards
5. Add or update tests as needed
6. Update documentation if necessary
7. Submit a pull request

## Pull Request Process

1. **Update documentation** if your changes affect the README or other docs
2. **Add tests** for new features or bug fixes
3. **Follow coding standards** (see below)
4. **Write clear commit messages**
5. **Keep pull requests focused** - one feature or fix per PR

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add user authentication endpoint

- Add JWT token generation
- Implement login/logout flow
- Add password hashing with bcrypt

Closes #123
```

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `style:` for formatting changes
- `refactor:` for code refactoring
- `test:` for adding tests
- `chore:` for maintenance tasks

## Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/) guidelines
- Use type hints for all function parameters and return values
- Keep functions focused and under 50 lines when possible
- Use docstrings for public functions and classes

### Example

```python
from typing import Optional

async def get_user(user_id: int) -> Optional[User]:
    """Retrieve a user by their ID.

    Args:
        user_id: The unique identifier for the user.

    Returns:
        The User object if found, None otherwise.

    Raises:
        DatabaseError: If there's a database connection issue.
    """
    async with get_session() as session:
        return await session.get(User, user_id)
```

### Code Organization

- Keep related code in the same module
- Use meaningful file and function names
- Separate concerns (routes, services, models)
- Avoid circular imports

## Testing

### Writing Tests

- Write tests for all new features and bug fixes
- Use descriptive test names
- Follow the Arrange-Act-Assert pattern
- Mock external dependencies

### Test Structure

```python
import pytest
from httpx import AsyncClient

class TestMemoryAPI:
    """Tests for memory endpoints."""

    async def test_create_memory_success(self, client: AsyncClient):
        """Test creating a memory with valid data."""
        # Arrange
        payload = {"key": "test_key", "value": "test_value"}

        # Act
        response = await client.post("/api/v1/memory", json=payload)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
```

## Documentation

- Update README.md for new features
- Add docstrings to all public functions
- Keep CHANGELOG.md updated
- Write clear commit messages

### Documentation Style

- Use clear, concise language
- Include code examples where helpful
- Keep documentation up-to-date with code changes

## Getting Help

If you need help:

1. Check existing documentation
2. Search existing issues
3. Create a new issue with the "question" label
4. Join our community channels (if available)

## Thank You!

Thank you for contributing to deepDDW! Your help is greatly appreciated.
