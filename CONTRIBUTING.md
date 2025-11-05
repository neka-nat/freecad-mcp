# Contributing to FreeCAD MCP

Thank you for your interest in contributing to FreeCAD MCP! This document provides guidelines and instructions for contributing.

## 🎯 Code of Conduct

This project follows a Code of Conduct. By participating, you are expected to:
- Be respectful and inclusive
- Accept constructive criticism
- Focus on what is best for the community
- Show empathy towards other community members

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- FreeCAD 0.21 or higher
- Git
- Basic understanding of Python and FreeCAD API

### Development Setup

1. **Fork the repository**
   ```bash
   # Fork on GitHub, then clone your fork
   git clone https://github.com/YOUR_USERNAME/freecad-mcp.git
   cd freecad-mcp
   ```

2. **Create a development branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Install dependencies**
   ```bash
   pip install -e .
   ```

4. **Install FreeCAD addon**
   ```bash
   # Copy addon to FreeCAD directory
   cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
   ```

5. **Start FreeCAD with RPC server**
   - Launch FreeCAD
   - Select "MCP Addon" workbench
   - Click "Start RPC Server"

## 📝 Development Guidelines

### Code Style

- Follow **PEP 8** Python style guide
- Use **type hints** for function parameters and return values
- Write **docstrings** for all public functions
- Keep functions **focused and small** (KISS principle)
- Avoid **code duplication** (DRY principle)
- Use **meaningful variable names**

### Code Structure

```python
def function_name(
    param1: str,
    param2: int,
    param3: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Brief description of function.
    
    Detailed description if needed.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        param3: Description of param3 (optional)
        
    Returns:
        Description of return value
        
    Example:
        {
            "param1": "value",
            "param2": 42
        }
    """
    # Implementation
    pass
```

### Commit Messages

Use **conventional commits** format:

```
type(scope): subject

body (optional)

footer (optional)
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test additions or modifications
- `refactor`: Code refactoring
- `style`: Code style changes (formatting, etc.)
- `chore`: Maintenance tasks

**Examples:**
```
feat(modeling): add support for NURBS surfaces

fix(assembly): correct constraint solving for Assembly3

docs(readme): add examples for advanced features

test(boolean): add test cases for intersection operation
```

### Branch Naming

Use descriptive branch names:
```
feature/add-nurbs-support
fix/assembly3-constraint-bug
docs/improve-quickstart-guide
test/add-boolean-tests
```

## 🧪 Testing

### Writing Tests

1. **Create test file**
   ```python
   # tests/test_your_feature.py
   import xmlrpc.client
   
   def test_your_feature():
       """Test your feature description."""
       server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
       
       # Test implementation
       result = server.your_function()
       assert result["success"] == True
   ```

2. **Run tests**
   ```bash
   # Run specific test
   python tests/test_your_feature.py
   
   # Run all tests
   python tests/run_all_tests.py
   ```

### Test Requirements

- All new features **must have tests**
- Tests should **verify actual behavior** with FreeCAD
- Tests should **clean up** after execution
- Tests should be **independent** (no dependencies between tests)
- Tests should **handle errors gracefully**

## 📚 Documentation

### Required Documentation

For each new feature, provide:

1. **Docstrings** in code (required)
2. **Examples** in docstrings (required)
3. **User guide** section in `docs/USER_GUIDE.md` (recommended)
4. **API reference** entry in `docs/API_REFERENCE.md` (recommended)
5. **Changelog** entry in `CHANGELOG.md` (required)

### Documentation Structure

```markdown
## Feature Name

Brief description of the feature.

### Usage

Description of how to use the feature.

### Parameters

- `param1` (type): Description
- `param2` (type): Description

### Returns

Description of return value.

### Example

```json
{
    "param1": "value",
    "param2": 42
}
```

### Notes

Additional notes or warnings.
```

## 🔧 Adding New Features

### 1. Plan Your Feature

- Check existing issues or create a new one
- Discuss your approach in the issue
- Get feedback before starting implementation

### 2. Implement the Feature

**For MCP Tools:**

1. **Create the implementation function**
   ```python
   # src/freecad_mcp/your_module.py
   def your_function(ctx, freecad, add_screenshot_if_available, ...):
       """Implementation."""
       try:
           # Execute code via XML-RPC
           code = """
   import FreeCAD
   # Your FreeCAD code here
   """
           result = freecad.execute_code(code)
           
           if result["success"]:
               response = [TextContent(type="text", text="Success message")]
               return add_screenshot_if_available(response, freecad.get_active_screenshot())
           else:
               return [TextContent(type="text", text=f"Error: {result['error']}")]
               
       except Exception as e:
           return [TextContent(type="text", text=f"Exception: {str(e)}")]
   ```

2. **Add the MCP tool wrapper**
   ```python
   # src/freecad_mcp/server.py
   from .your_module import your_function as _your_function
   
   @mcp.tool()
   def your_function_tool(
       ctx: Context,
       param1: str,
       param2: int,
   ) -> list[TextContent | ImageContent]:
       """Tool description.
       
       Args:
           param1: Description
           param2: Description
           
       Returns:
           Confirmation message and screenshot
           
       Example:
           {
               "param1": "value",
               "param2": 42
           }
       """
       freecad = get_freecad_connection()
       return _your_function(ctx, freecad, add_screenshot_if_available, param1, param2)
   ```

3. **Add tests**
   ```python
   # tests/test_your_feature.py
   def test_your_function():
       """Test your function."""
       # Test implementation
       pass
   ```

4. **Update documentation**
   - Add to `README.md` tool list
   - Add to `CHANGELOG.md`
   - Add to `docs/API_REFERENCE.md`
   - Add examples to `docs/USER_GUIDE.md`

### 3. Submit Your Contribution

1. **Ensure tests pass**
   ```bash
   python tests/run_all_tests.py
   ```

2. **Check code style**
   ```bash
   # Use linter if available
   pylint src/freecad_mcp/
   ```

3. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(module): add your feature"
   ```

4. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create Pull Request**
   - Go to GitHub and create a Pull Request
   - Fill in the PR template
   - Link related issues
   - Wait for review

## 🐛 Reporting Bugs

### Bug Report Template

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Create document
2. Execute tool with parameters: {...}
3. See error

**Expected behavior**
What you expected to happen.

**Actual behavior**
What actually happened.

**Screenshots**
If applicable, add screenshots.

**Environment:**
- OS: [e.g., Windows 11]
- Python version: [e.g., 3.10]
- FreeCAD version: [e.g., 0.21.2]
- freecad-mcp version: [e.g., 3.0]

**Additional context**
Any other relevant information.
```

## 💡 Feature Requests

### Feature Request Template

```markdown
**Is your feature request related to a problem?**
A clear description of what the problem is.

**Describe the solution you'd like**
A clear description of what you want to happen.

**Describe alternatives you've considered**
Any alternative solutions or features you've considered.

**Use case**
Describe how this feature would be used.

**Additional context**
Any other context or screenshots.
```

## 📋 Pull Request Process

1. **Before submitting:**
   - Run all tests and ensure they pass
   - Update documentation
   - Add changelog entry
   - Ensure code follows style guidelines

2. **PR Requirements:**
   - Clear description of changes
   - Link to related issues
   - Tests included
   - Documentation updated
   - No merge conflicts

3. **Review Process:**
   - Maintainers will review your PR
   - Address feedback and make requested changes
   - Once approved, maintainers will merge

4. **After merge:**
   - Your contribution will be in the next release
   - You'll be added to contributors list
   - Thank you! 🎉

## 🎓 Learning Resources

### FreeCAD API
- [FreeCAD Python Scripting](https://wiki.freecad.org/Python_scripting_tutorial)
- [FreeCAD API Documentation](https://freecad.github.io/SourceDoc/)
- [FreeCAD Forum](https://forum.freecad.org/)

### Model Context Protocol
- [MCP Documentation](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

### Python Best Practices
- [PEP 8 Style Guide](https://pep8.org/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Python Docstrings](https://pep257.readthedocs.io/)

## 📞 Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and general discussion
- **FreeCAD Forum**: For FreeCAD-specific questions

## 🙏 Recognition

All contributors will be:
- Listed in the Contributors section
- Mentioned in release notes
- Part of the FreeCAD MCP community

Thank you for contributing to FreeCAD MCP! 🚀

---

**Questions?** Feel free to ask in GitHub Discussions or open an issue.

