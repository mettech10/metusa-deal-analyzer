# 🔒 Security Documentation - Metusa Deal Analyzer

## Security Improvements Applied (Based on Claude Code Security Principles)

### 1. ✅ Input Validation & Sanitization
- **Postcode validation** - UK format regex validation
- **Numeric input validation** - Range checks (0-50M for price, 0-100K for rent)
- **Text input sanitization** - HTML escaping to prevent XSS
- **Length limits** - Max 500 chars for text, 10KB for JSON payloads
- **Enum validation** - Deal type must be BTL/BRR/HMO/FLIP

### 2. ✅ Rate Limiting
- **Analysis endpoint**: 10 requests per minute per IP
- **PDF generation**: 5 requests per minute per IP (more resource-intensive)
- **Default limits**: 200/day, 50/hour per IP
- Uses Flask-Limiter with Redis backend support

### 3. ✅ CORS Configuration
- **Restricted origins** - Only allows metusaproperty.co.uk and subdomain
- **Endpoint-specific rules** - Different CORS policies for different endpoints
- Prevents cross-origin attacks from unauthorized domains

### 4. ✅ Secret Management
- **Environment-based secrets** - SECRET_KEY from env var
- **Fallback to random** - Generates secure random key if not set
- **No hardcoded secrets** - Removed placeholder secret key

### 5. ✅ Error Handling
- **Generic error messages** - Don't expose internal details to clients
- **Logging** - Errors logged server-side for debugging
- **Specific status codes** - 400 for validation, 413 for too large, 429 for rate limit
- **Custom error handlers** - 404, 429, 500 handlers with JSON responses

### 6. ✅ Content Security
- **Content-Type validation** - Enforces application/json
- **JSON validation** - Uses get_json(silent=True) to handle malformed JSON
- **Secure headers** - X-Content-Type-Options: nosniff on PDF downloads

### 7. ✅ PDF Generation Security
- **HTML escaping** - All user input escaped before PDF generation
- **Jinja2 autoescape** - Template engine escapes by default
- **No file system access** - PDF generated in memory, not saved to disk

### 8. ✅ Deployment Security
- **Debug mode control** - FLASK_DEBUG env var controls debug mode
- **No debug in production** - Defaults to False
- **Host binding** - 0.0.0.0 for containerized deployments

---

## Security Checklist for Production Deployment

### Environment Variables
```bash
# Required
export SECRET_KEY="your-256-bit-secret-key-here"  # Generate with: openssl rand -hex 32
export FLASK_ENV="production"

# Optional but recommended
export FLASK_DEBUG="False"
export REDIS_URL="redis://localhost:6379/0"  # For rate limiting persistence
```

### Before Deploying
- [ ] Set strong SECRET_KEY (256-bit minimum)
- [ ] Set FLASK_ENV=production
- [ ] Set FLASK_DEBUG=False
- [ ] Configure Redis for rate limiting (prevents reset on restart)
- [ ] Enable HTTPS (SSL/TLS certificate)
- [ ] Set up Web Application Firewall (WAF)
- [ ] Configure logging and monitoring
- [ ] Set up automated security scanning

### Ongoing Security
- [ ] Monitor rate limit violations
- [ ] Review error logs weekly
- [ ] Update dependencies monthly
- [ ] Run security audits quarterly
- [ ] Backup data regularly

---

## Vulnerabilities Addressed

| Vulnerability | Mitigation | Status |
|---------------|------------|--------|
| XSS (Cross-Site Scripting) | HTML escaping, input sanitization | ✅ Fixed |
| SQL Injection | No database used (stateless) | ✅ N/A |
| CSRF | No state-changing GET requests | ✅ N/A |
| Rate Limiting Bypass | IP-based limits with Redis | ✅ Fixed |
| Information Disclosure | Generic error messages | ✅ Fixed |
| DoS (Large Payloads) | 10KB JSON limit | ✅ Fixed |
| CORS Misconfiguration | Restricted origins | ✅ Fixed |
| Insecure Secrets | Environment-based secrets | ✅ Fixed |
| Debug Mode Exposure | FLASK_DEBUG env control | ✅ Fixed |

---

## Testing Security

### Rate Limiting Test
```bash
# Should succeed (first 10)
for i in {1..12}; do
  curl -X POST http://localhost:5000/analyze \
    -H "Content-Type: application/json" \
    -d '{"address":"Test","postcode":"M1 1AA","dealType":"BTL","purchasePrice":"100000","monthlyRent":"500"}'
done
# 11th and 12th should return 429
```

### XSS Prevention Test
```bash
# Input with HTML/JS should be escaped
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"address":"<script>alert(1)</script>","postcode":"M1 1AA","dealType":"BTL","purchasePrice":"100000","monthlyRent":"500"}'
# Response should contain escaped HTML entities, not execute script
```

### Invalid Input Test
```bash
# Should return 400 for invalid data
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"address":"Test","postcode":"INVALID","dealType":"INVALID","purchasePrice":"-1000","monthlyRent":"abc"}'
# Should return validation errors
```

---

## Security Contacts

If you discover a security vulnerability:
1. **DO NOT** create a public issue
2. Email: security@metusaproperty.co.uk
3. Include steps to reproduce
4. Allow 48 hours for response

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Documentation](https://flask.palletsprojects.com/en/2.3.x/security/)
- [Claude Code Security](https://www.anthropic.com/news/claude-code-security)

---

**Last Updated:** 2026-02-20  
**Security Review Status:** ✅ Ready for Production
