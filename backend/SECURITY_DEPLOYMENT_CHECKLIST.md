# Security Deployment Checklist

## Pre-Deployment Verification

### 1. Environment Configuration
- [ ] Set `JWT_SECRET` to a cryptographically random 32+ character string
  ```bash
  # Generate with: openssl rand -base64 32
  JWT_SECRET=<generated-secret>
  ```
- [ ] Set `ADMIN_EMAIL` (e.g., admin@yourcompany.com)
- [ ] Set `ADMIN_PASSWORD` (minimum 12 characters, with uppercase, lowercase, numbers, symbols)
- [ ] Verify all other API keys are set (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
- [ ] Confirm FRONTEND_URL and BACKEND_URL are HTTPS in production
- [ ] Set `IS_PRODUCTION=true` if using HTTPS URLs

### 2. Database Setup
- [ ] PostgreSQL database is accessible
- [ ] DATABASE_URL environment variable is set correctly
- [ ] Database is initialized (schema.sql will run automatically on startup)
- [ ] Verify new tables created on first run:
  ```sql
  -- Check new security tables exist
  SELECT tablename FROM pg_tables 
  WHERE tablename IN ('token_blacklist', 'unsubscribe_nonces', 
                      'usage_tracking', 'refresh_token_versions', 'audit_logs');
  ```

### 3. Code Verification
- [ ] Python syntax is valid: `python3 -m py_compile server.py`
- [ ] All imports are available (run locally first)
- [ ] No hardcoded secrets in code (verified in code review)
- [ ] All security functions are imported and available

### 4. Security Headers
- [ ] HTTPS enforced for production
- [ ] Security headers are set (X-Content-Type-Options, X-Frame-Options, etc.)
- [ ] HSTS enabled (Strict-Transport-Security header)
- [ ] CSP policy configured

---

## Deployment Steps

### Step 1: Database Initialization
```bash
# The schema.sql runs automatically on startup, but verify it:
psql -U <db_user> -d <db_name> -c "\dt"

# Look for these tables:
# - token_blacklist
# - unsubscribe_nonces
# - usage_tracking
# - refresh_token_versions
# - audit_logs
```

### Step 2: Environment Variables
```bash
# Create .env file with required variables:
JWT_SECRET=<your-cryptographically-random-secret>
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=<strong-password-12+ chars>
DATABASE_URL=postgresql://user:password@host:port/dbname
FRONTEND_URL=https://app.example.com
BACKEND_URL=https://api.example.com

# All other API keys...
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
STRIPE_SECRET_KEY=...
# ... etc
```

### Step 3: First Startup
```bash
# On first startup, the system will:
# 1. Create admin account if ADMIN_EMAIL/ADMIN_PASSWORD provided
# 2. Initialize all database tables
# 3. Set up audit logging
# 4. Create usage tracking tables
# 5. Initialize token blacklist

# Monitor logs for success:
# "Admin account created: admin@example.com"
# "OutreachPilot started"
```

### Step 4: Post-Deployment Verification
```bash
# Test login endpoint
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"<password>"}'

# Verify token blacklist on logout
curl -X POST http://localhost:8000/api/auth/logout \
  -H "Authorization: Bearer <token>"

# Test rate limiting (should get 429 after 3 attempts)
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{"name":"Test","email":"test@test.com","password":"short"}'
done
```

---

## Security Configuration Recommendations

### 1. JWT Secret Management
- [ ] Use a high-entropy random string (minimum 32 characters)
- [ ] Store in secure secrets vault (AWS Secrets Manager, HashiCorp Vault, etc.)
- [ ] Rotate JWT_SECRET periodically (requires token re-authentication)
- [ ] Never commit to version control

### 2. Database Security
- [ ] Use strong database password
- [ ] Enable SSL/TLS for database connections
- [ ] Restrict database access to application servers only
- [ ] Enable database audit logging
- [ ] Regular backups with encryption

### 3. Admin Account Security
- [ ] Use strong, unique password (12+ characters)
- [ ] Store ADMIN_PASSWORD in secure secrets manager
- [ ] Change admin password after first login
- [ ] Enable MFA if supported by frontend
- [ ] Monitor admin account activity in audit logs

### 4. CORS/CSRF Configuration
- [ ] Verify FRONTEND_URL and BACKEND_URL are correct
- [ ] Use exact domain matching (implemented in code)
- [ ] Only allow HTTPS origins in production
- [ ] Test CSRF protection with different origins

### 5. Rate Limiting
- [ ] Review rate limits per endpoint (configured in code)
- [ ] Monitor for DDoS attacks in logs
- [ ] Consider Redis for distributed rate limiting
- [ ] Set up alerts for 429 errors

---

## Post-Deployment Testing

### Security Tests
```bash
# 1. Test JWT token blacklist on logout
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"<password>"}' | jq -r '.token')

# Use token - should work
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/me

# Logout - should blacklist token
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/logout

# Try using same token - should fail with 401
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/me

# 2. Test CORS with wrong origin
curl -X POST http://localhost:8000/api/leads \
  -H "Origin: https://evil.com" \
  -H "Content-Type: application/json" \
  -d '{"company":"test"}' \
  # Should return 403 CSRF validation failed

# 3. Test rate limiting
for i in {1..15}; do
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@test.com","password":"wrong"}'
done
# Should see 429 error after max attempts

# 4. Test SQL injection protection
curl -X POST http://localhost:8000/api/leads/import \
  -F "file=@<file>.csv" \
  -H "Authorization: Bearer $TOKEN"
# Should validate CSV format and content

# 5. Test unsubscribe nonce validation
# Try unsubscribing twice with same token
# Second attempt should fail with 400 "nonce already used"
```

### Audit Log Verification
```sql
-- Check audit logs for sensitive operations
SELECT user_id, action, resource, created_at 
FROM audit_logs 
ORDER BY created_at DESC 
LIMIT 20;

-- Should see:
-- - password_changed
-- - logout
-- - leads_imported
-- - admin_account_created
```

---

## Ongoing Security Maintenance

### Daily
- [ ] Monitor audit logs for suspicious activity
- [ ] Check error logs for security-related exceptions
- [ ] Monitor rate limit violations

### Weekly
- [ ] Review access patterns in activity logs
- [ ] Check for failed login attempts
- [ ] Verify all services are running with latest code

### Monthly
- [ ] Rotate JWT_SECRET (if applicable)
- [ ] Review database audit logs
- [ ] Update all dependencies for security patches
- [ ] Penetration testing (quarterly or as needed)

### Quarterly
- [ ] Full security audit
- [ ] Review rate limit effectiveness
- [ ] Audit user permissions and roles
- [ ] Update security policies

---

## Rollback Plan

If deployment issues occur:

1. **Token Blacklist Issues:**
   - Clear token_blacklist table if needed: `TRUNCATE token_blacklist;`
   - Users will need to re-login

2. **Admin Account Issues:**
   - If admin account cannot be created, check logs
   - Manually create: 
     ```sql
     INSERT INTO users (email, name, password_hash, role) 
     VALUES ('admin@company.com', 'Admin', '<hashed-password>', 'admin');
     ```

3. **Rate Limiting Issues:**
   - In-memory rate limiting resets on service restart
   - Check rate limit configuration in code

4. **Database Connectivity:**
   - Verify DATABASE_URL is correct
   - Check database is running and accessible
   - Verify user has correct permissions

---

## Monitoring and Alerting

### Key Metrics to Monitor
- [ ] Login success/failure rates
- [ ] Token blacklist growth (should be low)
- [ ] Rate limit violations per endpoint
- [ ] Database connection pool usage
- [ ] Error rate in logs

### Recommended Alerts
- [ ] 429 (Too Many Requests) - potential DDoS
- [ ] 401 (Unauthorized) - potential brute force
- [ ] 403 (Forbidden) - CSRF or permission issues
- [ ] Database errors - connection pool exhaustion
- [ ] Admin account creation attempts - new deployments

---

## Security Incident Response

### If Unauthorized Access Detected
1. Immediately revoke compromised JWT_SECRET
2. Force all users to re-authenticate
3. Review audit logs for affected accounts
4. Reset passwords for compromised accounts
5. Investigate token exposure vector

### If Data Breach Suspected
1. Enable comprehensive database audit logging
2. Export audit logs for analysis
3. Check token_blacklist for suspicious patterns
4. Review unsubscribe_nonces for replay attacks
5. Audit usage_tracking for unusual activity

---

## Compliance and Documentation

- [ ] Document all API endpoints and their security requirements
- [ ] Maintain audit log archive (compliance requirement)
- [ ] Document password policies and rotation schedule
- [ ] Create incident response runbooks
- [ ] Train team on security procedures
- [ ] Regular security awareness training

