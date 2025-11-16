# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Security Model

FreeCAD MCP is designed for **local development use only**. It provides AI models with direct control over FreeCAD, which includes the ability to execute arbitrary Python code.

### Known Security Considerations

1. **Arbitrary Code Execution**
   - The `execute_code` tool runs Python code directly in FreeCAD's environment
   - This is intentional functionality for maximum flexibility
   - **Mitigation**: Only use in trusted, local environments

2. **Unauthenticated RPC Server**
   - The XML-RPC server on `localhost:9875` accepts connections without authentication
   - Any local process can send commands
   - **Mitigation**: The server only binds to localhost by default

3. **No Input Sanitization**
   - Code and commands are executed as provided
   - **Mitigation**: This is expected behavior for a local development tool

### Recommendations

- **DO NOT** expose the RPC server port (9875) to external networks
- **DO NOT** run the server on systems with untrusted local processes
- **DO** use this tool only on development machines
- **DO** keep your system updated and free from malware
- **DO** review AI-generated code before it's executed

## Reporting a Vulnerability

If you discover a security vulnerability, please:

1. **DO NOT** open a public issue
2. Email the maintainer directly at nekanat.stock@gmail.com
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work with you to understand and address the issue.

## Future Security Enhancements (Planned)

- [ ] Optional token-based authentication for RPC server
- [ ] Code execution sandboxing options
- [ ] Rate limiting for RPC requests
- [ ] Audit logging for executed commands
- [ ] IP allowlist configuration

## Disclaimer

This software is provided "as is" without warranty of any kind. Users are responsible for ensuring their use of this tool complies with their organization's security policies and applicable laws.
