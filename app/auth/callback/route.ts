import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

// Simple Brevo email sender for welcome email (after verification)
async function sendWelcomeEmail(email: string, name?: string): Promise<boolean> {
  const apiKey = process.env.BREVO_API_KEY
  if (!apiKey) {
    console.warn("[Welcome Email] BREVO_API_KEY not set")
    return false
  }

  const greeting = name ? `Hi ${name.split(" ")[0]},` : "Hi,"
  
  const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light dark" />
  <title>Welcome to Metalyzi</title>
  <style>
    @media (prefers-color-scheme: dark) {
      .email-body { background-color: #0f0f0f !important; }
      .email-container { background-color: #1a1a1a !important; border-color: #2a2a2a !important; }
      .email-header { background-color: #111 !important; border-color: #2a2a2a !important; }
      .email-footer { border-color: #2a2a2a !important; }
      .email-text { color: #d1d5db !important; }
      .email-muted { color: #9ca3af !important; }
      .email-heading { color: #ffffff !important; }
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
                    <img src="https://metalyzi.co.uk/logo.png" alt="Metalyzi" width="40" height="40" style="border-radius:8px;display:block;" />
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
                ${greeting}
              </p>
              
              <p class="email-text" style="margin:0 0 32px;font-size:15px;color:#d1d5db;line-height:1.6;">
                Welcome to Metalyzi! Your email has been confirmed and your account is now active.
              </p>

              <p class="email-text" style="margin:0 0 32px;font-size:15px;color:#d1d5db;line-height:1.6;">
                Start analysing property deals with AI in seconds:
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
                <tr>
                  <td style="background-color:#ffffff;border-radius:8px;padding:14px 32px;text-align:center;">
                    <a href="https://metalyzi.co.uk/analyse" style="color:#000000;font-size:15px;font-weight:600;text-decoration:none;display:inline-block;">
                      Start Analysing →
                    </a>
                  </td>
                </tr>
              </table>

              <table class="email-container" width="100%" cellpadding="0" cellspacing="0" style="background-color:#111;border:1px solid #2a2a2a;border-radius:8px;margin-bottom:32px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 14px;font-size:13px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">What you can do</p>
                    <ul style="margin:0;padding:0 0 0 18px;color:#d1d5db;font-size:14px;line-height:2;">
                      <li>Analyse any UK property deal in seconds</li>
                      <li>Get instant cashflow, yield, and deal scores</li>
                      <li>View comparable sales and rental data</li>
                      <li>Save and track your analyses</li>
                    </ul>
                  </td>
                </tr>
              </table>

              <p class="email-muted" style="margin:0;font-size:14px;color:#9ca3af;line-height:1.6;">
                If you have any questions, just reply to this email or <a href="mailto:support@metalyzi.co.uk" style="color:#d1d5db;text-decoration:underline;">contact support</a>.
              </p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td class="email-footer" style="padding:20px 36px 28px;border-top:1px solid #2a2a2a;">
              <p style="margin:0;font-size:12px;color:#4b5563;line-height:1.6;">
                You're receiving this email because you signed up for Metalyzi.<br />
                © ${new Date().getFullYear()} Metalyzi. All rights reserved.
              </p>
            </td>
          </tr>
          
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`

  try {
    const res = await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": apiKey,
      },
      body: JSON.stringify({
        sender: { name: "Metalyzi", email: "noreply@metalyzi.co.uk" },
        to: [{ email }],
        subject: "Welcome to Metalyzi!",
        htmlContent,
      }),
    })

    if (!res.ok) {
      console.error("[Welcome Email] Failed:", res.status, await res.text())
      return false
    }

    console.log(`[Welcome Email] ✓ Sent to ${email}`)
    return true
  } catch (err) {
    console.error("[Welcome Email] Error:", err)
    return false
  }
}

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get("code")
  const next = searchParams.get("next") ?? "/analyse"

  if (code) {
    const supabase = await createClient()
    const { data, error } = await supabase.auth.exchangeCodeForSession(code)
    
    if (!error && data.session) {
      const email = data.session.user.email
      const name = data.session.user.user_metadata?.full_name || data.session.user.user_metadata?.name
      const provider = data.session.user.app_metadata?.provider
      
      // Send welcome email for new signups (both Google and email)
      // For Google: immediate welcome
      // For email: welcome after they verify (if verification enabled in Supabase)
      if (email) {
        sendWelcomeEmail(email, name).catch(console.error)
      }
      
      // Check if email needs verification (for email/password signups)
      // Google users are pre-verified by Google
      if (provider === "email" && !data.session.user.email_confirmed_at) {
        // Email not verified yet - redirect to verification page
        return NextResponse.redirect(`${origin}/verify-email`)
      }
      
      // Google users or verified email users - go straight to app
      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  // Auth error -- redirect to login with error
  return NextResponse.redirect(`${origin}/login?error=auth`)
}