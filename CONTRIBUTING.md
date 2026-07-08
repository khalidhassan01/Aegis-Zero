# Contributing to Aegis-Zero

> **Advanced Security & Trust Framework for Autonomous AI Agents**

**We welcome contributions!** Aegis-Zero is an open-source project and we're excited to have you contribute.

---

## 📋 **Table of Contents**

- [Code of Conduct](#-code-of-conduct)
- [How Can I Contribute?](#-how-can-i-contribute)
- [Getting Started](#-getting-started)
- [Development Environment](#-development-environment)
- [Pull Request Process](#-pull-request-process)
- [Coding Standards](#-coding-standards)
- [Testing Requirements](#-testing-requirements)
- [Commit Message Guidelines](#-commit-message-guidelines)
- [Reporting Issues](#-reporting-issues)
- [Community](#-community)

---

## 🤝 **Code of Conduct**

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

---

## 💡 **How Can I Contribute?**

### Reporting Bugs
- Open an issue with a clear title and description
- Include steps to reproduce
- Include relevant logs or error messages
- Include your environment (Python version, OS, etc.)

### Suggesting Enhancements
- Open an issue with your enhancement idea
- Explain the use case and benefits
- Include any relevant research or examples

### Submitting Pull Requests
- Fork the repository
- Create a feature branch
- Implement your changes
- Add tests for new functionality
- Ensure all existing tests pass
- Submit a pull request

### Improving Documentation
- Fix typos or unclear wording
- Add missing documentation
- Improve examples
- Update outdated information

---

## 🚀 **Getting Started**

### Prerequisites

- Python 3.10+
- Git
- Ollama (for local AI inference)
- Qdrant (for vector database)

### Installation

```bash
# Clone the repository
git clone https://github.com/khalidhassan01/Aegis-Zero.git
cd Aegis-Zero

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

---

## 💻 **Development Environment**

### Setting Up Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull required models
ollama pull gemma4:26b      # aegis-deep
ollama pull gemma4:e4b      # aegis-fast
ollama pull nomic-embed-text # embeddings
```

### Setting Up Qdrant

```bash
# Run Qdrant in Docker
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

### Environment Variables

```bash
# Required
export AEGIS_QDRANT_HOST=127.0.0.1
export AEGIS_QDRANT_PORT=6333
export AEGIS_VECTOR_SIZE=768
export AEGIS_EMBED_MODEL=nomic-embed-text

# Optional (Telegram)
export AEGIS_TELEGRAM_BOT_TOKEN=your_token
export AEGIS_TELEGRAM_CHAT_ID=your_chat_id

# Optional (Models)
export AEGIS_FAST_MODEL=aegis-fast
export AEGIS_DEEP_MODEL=aegis-deep
```

---

## 🔄 **Pull Request Process**

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes** following our coding standards
5. **Add tests** for new functionality
6. **Run tests** to ensure nothing is broken:
   ```bash
   python3 -m unittest discover -s . -p "test_*.py"
   ```
7. **Commit your changes** with a descriptive message:
   ```bash
   git commit -m "Add feature: your feature description"
   ```
8. **Push** your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
9. **Open a Pull Request** to the main repository

### Pull Request Requirements

- [ ] Clear title describing the change
- [ ] Detailed description of the changes
- [ ] All tests pass
- [ ] New tests added for new functionality
- [ ] Code follows our coding standards
- [ ] Documentation updated (if applicable)
- [ ] No breaking changes (unless approved)

---

## 📝 **Coding Standards**

### Python Code

- **Type Hints:** All public functions must have type hints
- **Docstrings:** All classes and public functions must have docstrings
- **Imports:** Organized by type (standard, third-party, local)
- **Naming:** Follow PEP 8 conventions
- **Line Length:** Maximum 120 characters
- **Error Handling:** Use try/except with proper logging
- **Logging:** Use structured JSON logging

### Example

```python
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class MyClass:
    """Docstring explaining the class purpose."""
    
    def my_method(self, param: str, count: int = 0) -> Optional[str]:
        """
        Docstring explaining the method.
        
        Args:
            param: Description of param
            count: Description of count
            
        Returns:
            Description of return value
        """
        try:
            # Implementation
            return result
        except Exception as e:
            logger.error(f"Error in my_method: {e}")
            return None
```

### File Headers

All Python files should start with:

```python
# AEGIS ZERO - [Component Name] v1.0
# Part of the Aegis-Zero Agent Framework
# Author: Khalid Hassan
# License: MIT
# Repository: https://github.com/khalidhassan01/Aegis-Zero
```

---

## 🧪 **Testing Requirements**

### Test Coverage

- All new functionality must have tests
- All existing tests must pass
- Tests should cover edge cases
- Tests should mock external dependencies

### Running Tests

```bash
# Run all tests
python3 -m unittest discover -s . -p "test_*.py"

# Run specific test file
python3 test_harness_tools.py

# Run with verbose output
python3 -m unittest discover -s . -p "test_*.py" -v
```

### Test Structure

- Test files: `test_*.py`
- Test classes: `*Tests(unittest.TestCase)`
- Test methods: `test_*()`
- Use mocking for external dependencies

---

## 📝 **Commit Message Guidelines**

### Format

```
type(scope): subject

body

footer
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or fixing tests
- `chore`: Maintenance tasks
- `build`: Build system changes
- `ci`: CI/CD changes

### Examples

```bash
# Good
git commit -m "feat(puppeteer): add parallel forge support"
git commit -m "fix(tool_policy): correct path validation"
git commit -m "docs: update README with installation instructions"
git commit -m "test: add policy enforcement tests"

# Bad (avoid)
git commit -m "fixed bug"
git commit -m "changes"
git commit -m "wip"
```

---

## 🐛 **Reporting Issues**

### Bug Reports

When reporting a bug, please include:

1. **Title:** Clear and descriptive
2. **Description:** Detailed description of the issue
3. **Steps to Reproduce:** Clear steps to reproduce the issue
4. **Expected Behavior:** What you expected to happen
5. **Actual Behavior:** What actually happened
6. **Environment:**
   - Python version
   - Operating System
   - Dependencies versions
7. **Logs/Errors:** Any relevant error messages or logs
8. **Screenshots:** If applicable, screenshots of the issue

### Feature Requests

When requesting a feature, please include:

1. **Title:** Clear and descriptive
2. **Description:** Detailed description of the feature
3. **Use Case:** How this feature would be used
4. **Benefits:** Why this feature is valuable
5. **Examples:** Any relevant examples or references

---

## 🤝 **Community**

### Communication

- **GitHub Issues:** https://github.com/khalidhassan01/Aegis-Zero/issues
- **GitHub Discussions:** https://github.com/khalidhassan01/Aegis-Zero/discussions

### Contributor Recognition

All contributions are valued and recognized. Contributors will be:
- Added to the CONTRIBUTORS.md file
- Mentioned in release notes
- Recognized in the project documentation

### Code Reviews

All pull requests will be reviewed by maintainers. Please be patient and responsive to feedback.

---

## 📚 **Additional Resources**

- [README.md](README.md) - Project overview
- [AEGIS_ZERO_DEVELOPER_BRIEF.html](AEGIS_ZERO_DEVELOPER_BRIEF.html) - Developer guide
- [AEGIS_INTEGRATION_GUIDE.md](AEGIS_INTEGRATION_GUIDE.md) - Integration instructions
- [Logo-Designs/BRANDING.md](Logo-Designs/BRANDING.md) - Branding guidelines

---

## ✅ **Checklist Before Submitting**

- [ ] I have read the [Code of Conduct](CODE_OF_CONDUCT.md)
- [ ] My code follows the coding standards
- [ ] I have added tests for new functionality
- [ ] All existing tests pass
- [ ] My commit messages follow the guidelines
- [ ] My pull request has a clear title and description
- [ ] I have updated documentation if needed

---

**Thank you for contributing to Aegis-Zero!** 🚀

*We appreciate your time and effort in making Aegis-Zero better.*
