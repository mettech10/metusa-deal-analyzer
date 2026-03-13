/**
 * Brevo Transactional Email helpers
 * Sends welcome and receipt emails via Brevo SMTP API.
 *
 * Required env vars:
 *   BREVO_API_KEY        — your Brevo API key
 *   BREVO_SENDER_EMAIL   — verified sender address (default: noreply@metalyzi.co.uk)
 */

async function sendBrevoEmail(
  to: string,
  subject: string,
  htmlContent: string,
): Promise<boolean> {
  const apiKey = process.env.BREVO_API_KEY
  const senderEmail = process.env.BREVO_SENDER_EMAIL ?? "noreply@metalyzi.co.uk"

  if (!apiKey) {
    console.warn("[Brevo Email] BREVO_API_KEY not set, skipping email to", to)
    return false
  }

  try {
    const res = await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": apiKey,
      },
      body: JSON.stringify({
        sender: { name: "Metalyzi", email: senderEmail },
        to: [{ email: to }],
        subject,
        htmlContent,
      }),
    })

    if (!res.ok) {
      console.error("[Brevo Email] Send failed:", res.status, await res.text())
      return false
    }

    console.log(`[Brevo Email] ✓ Sent "${subject}" → ${to}`)
    return true
  } catch (err) {
    console.error("[Brevo Email] Network error:", err)
    return false
  }
}

// ─── Email Templates ─────────────────────────────────────────────────────────

function baseTemplate(content: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Metalyzi</title>
</head>
<body style="margin:0;padding:0;background:#0f0f0f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f0f;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#1a1a1a;border-radius:12px;border:1px solid #2a2a2a;overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="background:#111;padding:28px 36px;border-bottom:1px solid #2a2a2a;">
              <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">Metalyzi</span>
              <span style="font-size:13px;color:#6b7280;margin-left:8px;">AI Property Analysis</span>
            </td>
          </tr>
          <!-- Content -->
          <tr>
            <td style="padding:36px;">
              ${content}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 36px 28px;border-top:1px solid #2a2a2a;">
              <p style="margin:0;font-size:12px;color:#4b5563;line-height:1.6;">
                You're receiving this email because you interacted with Metalyzi.<br />
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
}

function waitlistEmailHtml(): string {
  return baseTemplate(`
    <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">
      You're on the waitlist! 🎉
    </h1>
    <p style="margin:0 0 24px;font-size:15px;color:#9ca3af;line-height:1.6;">
      Thanks for joining the Metalyzi waitlist. We'll let you know as soon as early access opens up.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="background:#111;border:1px solid #2a2a2a;border-radius:8px;margin-bottom:28px;">
      <tr>
        <td style="padding:20px 24px;">
          <p style="margin:0 0 14px;font-size:13px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">What's coming</p>
          <ul style="margin:0;padding:0 0 0 18px;color:#d1d5db;font-size:14px;line-height:2;">
            <li>AI-powered property deal analysis</li>
            <li>Instant cashflow &amp; yield calculations</li>
            <li>Comparable sales &amp; rental data</li>
            <li>Smart deal scoring system</li>
          </ul>
        </td>
      </tr>
    </table>

    <p style="margin:0;font-size:14px;color:#6b7280;line-height:1.6;">
      We'll be in touch soon. In the meantime, feel free to reply to this email if you have any questions.
    </p>
  `)
}

function signUpWelcomeEmailHtml(name?: string): string {
  const greeting = name ? `Welcome, ${name.split(" ")[0]}!` : "Welcome to Metalyzi!"
  return baseTemplate(`
    <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">
      ${greeting} 👋
    </h1>
    <p style="margin:0 0 28px;font-size:15px;color:#9ca3af;line-height:1.6;">
      Your account is ready. Start analysing property deals with AI in seconds.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="background:#111;border:1px solid #2a2a2a;border-radius:8px;margin-bottom:28px;">
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

    <a href="https://metalyzi.co.uk/analyse"
       style="display:inline-block;background:#ffffff;color:#000000;font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;letter-spacing:0.2px;">
      Start Analysing →
    </a>
  `)
}

function receiptEmailHtml(plan: string, amount: string): string {
  const planLabel =
    plan === "pay_per_deal"
      ? "Pay Per Deal"
      : plan === "pro"
      ? "Pro Plan"
      : plan === "unlimited"
      ? "Unlimited Plan"
      : "Subscription"

  return baseTemplate(`
    <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">
      Payment confirmed ✓
    </h1>
    <p style="margin:0 0 28px;font-size:15px;color:#9ca3af;line-height:1.6;">
      Thanks for subscribing to Metalyzi. Your access is now active.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="background:#111;border:1px solid #2a2a2a;border-radius:8px;margin-bottom:28px;">
      <tr>
        <td style="padding:20px 24px;">
          <p style="margin:0 0 16px;font-size:13px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Receipt summary</p>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="font-size:14px;color:#9ca3af;padding:6px 0;border-bottom:1px solid #2a2a2a;">Plan</td>
              <td align="right" style="font-size:14px;color:#ffffff;font-weight:600;padding:6px 0;border-bottom:1px solid #2a2a2a;">${planLabel}</td>
            </tr>
            <tr>
              <td style="font-size:14px;color:#9ca3af;padding:6px 0 0;">Amount</td>
              <td align="right" style="font-size:14px;color:#ffffff;font-weight:600;padding:6px 0 0;">${amount}</td>
            </tr>
          </table>
        </td>
      </tr>
    </table>

    <a href="https://metalyzi.co.uk/analyse"
       style="display:inline-block;background:#ffffff;color:#000000;font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;letter-spacing:0.2px;">
      Start Analysing →
    </a>

    <p style="margin:20px 0 0;font-size:13px;color:#6b7280;line-height:1.6;">
      If you have any questions about your plan, just reply to this email.
    </p>
  `)
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function sendWaitlistWelcomeEmail(email: string): Promise<boolean> {
  return sendBrevoEmail(email, "You're on the Metalyzi waitlist!", waitlistEmailHtml())
}

export function sendSignUpWelcomeEmail(email: string, name?: string): Promise<boolean> {
  return sendBrevoEmail(email, "Welcome to Metalyzi!", signUpWelcomeEmailHtml(name))
}

export function sendSubscriptionReceiptEmail(
  email: string,
  plan: string,
  amount: string,
): Promise<boolean> {
  return sendBrevoEmail(email, "Your Metalyzi payment is confirmed", receiptEmailHtml(plan, amount))
}
