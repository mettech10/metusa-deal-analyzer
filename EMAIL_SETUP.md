# Email Verification Setup for Metalyzi

## Supabase Dashboard Configuration

### Step 1: Enable Email Confirmation

1. Go to Supabase Dashboard → Authentication → Providers
2. Find "Email" provider
3. Enable "Confirm email" toggle
4. Set "Confirmation URL" to: `https://metalyzi.co.uk/auth/callback`

### Step 2: Configure Email Template

Go to Supabase Dashboard → Authentication → Email Templates → "Confirm signup"

**Subject:**
```
Confirm your email - Metalyzi
```

**HTML Body:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light dark" />
  <title>Confirm your email - Metalyzi</title>
  <style>
    @media (prefers-color-scheme: dark) {
      .email-body { background-color: #0f0f0f !important; }
      .email-container { background-color: #1a1a1a !important; border-color: #2a2a2a !important; }
      .email-header { background-color: #111 !important; border-color: #2a2a2a !important; }
      .email-footer { border-color: #2a2a2a !important; }
      .email-text { color: #d1d5db !important; }
      .email-muted { color: #9ca3af !important; }
    }
  </style>
</head>
<body class="email-body" style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background-color:#0f0f0f;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f;padding:40px 16px;">
    <tr>
      <td align="center">
        <table class="email-container" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background-color:#1a1a1a;border-radius:12px;border:1px solid #2a2a2a;overflow:hidden;">
          
          <!-- Header -->
          <tr>
            <td class="email-header" style="background-color:#111;padding:28px 36px;border-bottom:1px solid #2a2a2a;">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding-right:12px;">
                    <div style="width:40px;height:40px;background:linear-gradient(135deg,#1B1F3B 0%,#D4AF37 100%);border-radius:8px;display:flex;align-items:center;justify-content:center;color:white;font-weight:bold;font-size:20px;">M</div>
                  </td>
                  <td>
                    <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">Metalyzi</span>
                    <br/>
                    <span style="font-size:13px;color:#6b7280;">AI Property Analysis</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          
          <!-- Content -->
          <tr>
            <td style="padding:36px;">
              <p class="email-text" style="margin:0 0 24px;font-size:15px;color:#d1d5db;line-height:1.6;">
                Hi,
              </p>
              
              <p class="email-text" style="margin:0 0 32px;font-size:15px;color:#d1d5db;line-height:1.6;">
                Welcome to Metalyzi! Please confirm your email address to get started:
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
                <tr>
                  <td style="background-color:#ffffff;border-radius:8px;padding:14px 32px;text-align:center;">
                    <a href="{{ .ConfirmationURL }}" style="color:#000000;font-size:15px;font-weight:600;text-decoration:none;display:inline-block;">
                      Confirm email
                    </a>
                  </td>
                </tr>
              </table>

              <p class="email-muted" style="margin:0;font-size:14px;color:#9ca3af;line-height:1.6;">
                If this is a mistake or you didn't initiate this request, <a href="mailto:support@metalyzi.co.uk" style="color:#d1d5db;text-decoration:underline;">contact Metalyzi support</a>.
              </p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td class="email-footer" style="padding:20px 36px 28px;border-top:1px solid #2a2a2a;">
              <p style="margin:0;font-size:12px;color:#4b5563;line-height:1.6;">
                © {{ .CurrentYear }} Metalyzi. All rights reserved.
              </p>
            </td>
          </tr>
          
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

### Step 3: Redirect URLs

In Supabase Dashboard → Authentication → URL Configuration:

- **Site URL:** `https://metalyzi.co.uk`
- **Redirect URLs:** Add `https://metalyzi.co.uk/auth/callback`

### Step 4: Test the Flow

1. Sign up with a new email
2. Check inbox for verification email
3. Click "Confirm email" button
4. Should redirect to `/analyse?welcome=true`
5. Welcome email will be sent automatically

## Important Notes

- The confirmation URL must match your callback route exactly
- Email templates support Handlebars syntax: `{{ .ConfirmationURL }}`, `{{ .Email }}`, `{{ .CurrentYear }}`
- Dark mode is automatic via CSS media queries
- Logo uses CSS gradient (replace with actual logo URL if available)