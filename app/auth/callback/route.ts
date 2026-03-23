import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

// Simple Brevo email sender
async function sendWelcomeEmail(email: string, name?: string): Promise<boolean> {
  const apiKey = process.env.BREVO_API_KEY
  if (!apiKey) {
    console.warn("[Welcome Email] BREVO_API_KEY not set")
    return false
  }

  const greeting = name ? `Welcome, ${name.split(" ")[0]}!` : "Welcome to Metalyzi!"
  
  const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Welcome to Metalyzi</title>
</head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background-color:#0f0f0f;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background-color:#1a1a1a;border-radius:12px;border:1px solid #2a2a2a;overflow:hidden;">
          <tr>
            <td style="background-color:#111;padding:28px 36px;border-bottom:1px solid #2a2a2a;">
              <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">Metalyzi</span>
              <span style="font-size:13px;color:#6b7280;margin-left:8px;">AI Property Analysis</span>
            </td>
          </tr>
          <tr>
            <td style="padding:36px;">
              <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">${greeting} 👋</h1>
              <p style="margin:0 0 28px;font-size:15px;color:#9ca3af;line-height:1.6;">
                Your account is ready. Start analysing property deals with AI in seconds.
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#111;border:1px solid #2a2a2a;border-radius:8px;margin-bottom:28px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 14px;font-size:13px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Get started</p>
                    <ul style="margin:0;padding:0 0 0 18px;color:#d1d5db;font-size:14px;line-height:2;">
                      <li>Enter any UK property address to analyse a deal</li>
                      <li>Get cashflow, yield, and deal score instantly</li>
                      <li>View comparable sales and rentals nearby</li>
                      <li>Save your analyses and track deals over time</li>
                    </ul>
                  </td>
                </tr>
              </table>
              <a href="https://metalyzi.co.uk/analyse" style="display:inline-block;background:#ffffff;color:#000000;font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;letter-spacing:0.2px;">Start Analysing →</a>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 36px 28px;border-top:1px solid #2a2a2a;">
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
      
      // Send welcome email asynchronously (don't block redirect)
      // Note: This will send on every login. To track first-time only,
      // you'd need a user_profiles table with welcome_email_sent column
      if (email) {
        sendWelcomeEmail(email, name).catch(console.error)
      }

      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  // Auth error -- redirect to login with error
  return NextResponse.redirect(`${origin}/login?error=auth`)
}