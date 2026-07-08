# Security Policy

## 🔒 Security Commitment

Aegis-Zero takes security seriously. We are committed to ensuring the security and privacy of our users' data and systems. This document outlines our security policies and procedures.

---

## 📋 Supported Versions

| Version | Supported | Security Updates |
|---------|-----------|------------------|
| 7.0.x   | ✅ Yes     | ✅ Active         |
| 6.x     | ❌ No      | ❌ End of Life    |
| < 6.0   | ❌ No      | ❌ End of Life    |

**Only the latest version (7.0.x) receives security updates.**

---

## 🐛 Reporting a Vulnerability

### Security Vulnerability Reporting

**DO NOT** report security vulnerabilities through public GitHub issues, discussions, or email.

Instead, please report security vulnerabilities by:

1. **Email:** Send a detailed report to [khalidhassan01](https://github.com/khalidhassan01) via GitHub private message
2. **Include:**
   - Detailed description of the vulnerability
   - Steps to reproduce
   - Impact assessment
   - Potential mitigation
   - Your contact information (optional)

### Response Time

| Severity | Response Time | Resolution Time |
|----------|---------------|------------------|
| Critical | 24 hours | 72 hours |
| High | 48 hours | 1 week |
| Medium | 1 week | 2 weeks |
| Low | 2 weeks | 1 month |

---

## 🛡️ Security Features

Aegis-Zero implements a **6-layer security model**:

### Layer 0: Tailscale Mesh Networking
- **Zero public ports** - Server is invisible to the internet
- **Mutual TLS authentication** - All connections are encrypted
- **Mesh networking** - Secure device-to-device communication

### Layer 1: Oracle VCN Firewall
- **DENY_ALL ingress** - No inbound connections allowed
- **HTTPS-only egress** - Outbound connections restricted to port 443
- **Static IP reservation** - Prevents IP address changes

### Layer 2: OS Hardening
- **iptables DROP policy** - Default deny all inbound traffic
- **fail2ban** - Automatic brute force protection (5 retries = 1 hour ban)
- **Metadata endpoint blocked** - Prevents Oracle credential exfiltration
- **Unattended security upgrades** - Automatic security patching

### Layer 3: Nginx Reverse Proxy
- **Localhost binding only** - No external IP binding
- **SSL termination** - Internal HTTPS encryption
- **Service routing** - Secure internal service communication

### Layer 4: Application Security
- **Command approval required** - All commands must be explicitly approved
- **PII redaction** - Personal information removed from external calls
- **Secret scanning** - API keys and credentials never exposed
- **Diff preview** - File changes reviewed before execution
- **Stealth browser** - Private browsing mode for research

### Layer 5: Session Security
- **No reverse access** - Clients cannot access the server
- **Session continuity IDs** - Consistent session tracking
- **Credential pool isolation** - Separate credentials for each service

---

## 🔍 Security Audit

### Regular Audits
- **Nightly health checks** via `hermes doctor`
- **Automated security scanning** of all commits
- **Dependency vulnerability scanning**
- **Code review** for all pull requests

### Third-Party Dependencies

| Dependency | Version | Security Status |
|------------|---------|-----------------|
| ollama | >= 0.3.0 | ✅ No known vulnerabilities |
| qdrant-client | >= 1.8.0 | ✅ No known vulnerabilities |
| httpx | >= 0.26.0 | ✅ No known vulnerabilities |

All dependencies are regularly scanned for vulnerabilities.

---

## 🔐 Security Best Practices

### For Users

1. **Never share credentials** - Keep your API keys and tokens private
2. **Use strong passwords** - For all services and accounts
3. **Keep software updated** - Regularly update Aegis-Zero and dependencies
4. **Monitor access** - Review who has access to your instance
5. **Backup regularly** - Backup your configuration and data

### For Developers

1. **Follow secure coding practices** - OWASP guidelines
2. **Sanitize all inputs** - Never trust user input
3. **Use parameterized queries** - Prevent SQL injection
4. **Validate all outputs** - Prevent XSS and injection
5. **Log securely** - Never log sensitive information

---

## 📚 Security Documentation

- [AEGIS_ZERO_DEVELOPER_BRIEF.html](AEGIS_ZERO_DEVELOPER_BRIEF.html) - Detailed security architecture
- [aegis.conf.yaml.txt](aegis.conf.yaml.txt) - Security configuration
- [AUDIT_REPORT.md](AUDIT_REPORT.md) - Security audit results

---

## 📞 Security Contact

For security-related questions or concerns:

- **GitHub:** [khalidhassan01](https://github.com/khalidhassan01)
- **Repository:** https://github.com/khalidhassan01/Aegis-Zero

**For security vulnerabilities, please use private communication channels.**

---

## ✅ Security Commitments

We commit to:

- [x] **Responsible disclosure** - Private reporting and coordinated fixes
- [x] **Timely updates** - Security patches released promptly
- [x] **Transparency** - Security advisories published for all users
- [x] **Continuous monitoring** - Proactive security scanning and auditing
- [x] **Secure defaults** - Security is enabled by default, not optional

---

**Last Updated:** July 8, 2026

*Security Policy v1.0 - Aegis-Zero Project*
