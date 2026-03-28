/**
 * Brevo Transactional Email helpers
 * Sends waitlist, verification, welcome, and receipt emails via Brevo SMTP API.
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

  const replyToEmail = process.env.BREVO_REPLY_TO_EMAIL ?? process.env.BREVO_SENDER_EMAIL ?? senderEmail

  try {
    const res = await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": apiKey,
      },
      body: JSON.stringify({
        sender: { name: "Metalyzi", email: senderEmail },
        replyTo: { email: replyToEmail },
        to: [{ email: to }],
        subject,
        htmlContent,
      }),
    })

    const responseText = await res.text()
    if (!res.ok) {
      console.error("[Brevo Email] Send failed:", res.status, responseText)
      return false
    }

    console.log(`[Brevo Email] ✓ Sent "${subject}" → ${to} | Response: ${responseText}`)
    return true
  } catch (err) {
    console.error("[Brevo Email] Network error:", err)
    return false
  }
}

// ─── Shared helpers ───────────────────────────────────────────────────────────

function logoBlock(): string {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://metalyzi.co.uk"
  return `
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
      <tr>
        <td align="center">
          <img
            src="${siteUrl}/logo.png"
            alt="Metalyzi"
            width="48"
            height="48"
            style="display:block;border-radius:10px;border:0;"
            onerror="this.style.display='none'"
          />
          <div style="margin-top:10px;font-size:20px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">
            Metalyzi
          </div>
        </td>
      </tr>
    </table>`
}

function emailFooter(): string {
  return `
    <tr>
      <td style="padding:20px 36px 28px;border-top:1px solid #2a2a2a;">
        <p style="margin:0;font-size:12px;color:#4b5563;line-height:1.6;text-align:center;">
          © 2025 Metalyzi. All rights reserved.
        </p>
      </td>
    </tr>`
}

function baseTemplate(content: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Metalyzi</title>
  <style>
    @media only screen and (max-width: 600px) {
      .email-wrapper { padding: 20px 8px !important; }
      .email-card { border-radius: 0 !important; }
      .email-body { padding: 24px 20px !important; }
      .email-footer-cell { padding: 16px 20px 24px !important; }
      .cta-button { display: block !important; text-align: center !important; }
    }
  </style>
</head>
<body style="margin:0;padding:0;background:#0f0f0f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <table width="100%" cellpadding="0" cellspacing="0" class="email-wrapper" style="background:#0f0f0f;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" class="email-card" style="max-width:560px;width:100%;background:#1a1a1a;border-radius:12px;border:1px solid #2a2a2a;overflow:hidden;">
          <!-- Content -->
          <tr>
            <td class="email-body" style="padding:36px;">
              ${content}
            </td>
          </tr>
          <!-- Footer -->
          ${emailFooter()}
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`
}

// ─── Email Templates ─────────────────────────────────────────────────────────

function verificationEmailHtml(verificationUrl: string): string {
  return baseTemplate(`
    ${logoBlock()}

    <h1 style="margin:0 0 12px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;text-align:center;">
      Confirm your email address
    </h1>
    <p style="margin:0 0 28px;font-size:15px;color:#9ca3af;line-height:1.7;text-align:center;">
      Thanks for signing up to Metalyzi. Click the button below to verify
      your email and get started with smarter property investment.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
      <tr>
        <td align="center">
          <a href="${verificationUrl}"
             class="cta-button"
             style="display:inline-block;background:#ffffff;color:#0f0f0f;font-size:15px;font-weight:700;padding:14px 36px;border-radius:8px;text-decoration:none;letter-spacing:0.2px;">
            Verify Email
          </a>
        </td>
      </tr>
    </table>

    <p style="margin:0;font-size:12px;color:#4b5563;line-height:1.6;text-align:center;">
      If you didn't create a Metalyzi account, you can safely ignore this email.<br />
      This link expires in 24 hours.
    </p>
  `)
}

function welcomeEmailHtml(): string {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://metalyzi.co.uk"
  const dashboardUrl = `${siteUrl}/analyse`

  return baseTemplate(`
    ${logoBlock()}

    <h1 style="margin:0 0 12px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;text-align:center;">
      Welcome to Metalyzi
    </h1>
    <p style="margin:0 0 28px;font-size:15px;color:#9ca3af;line-height:1.7;text-align:center;">
      You're all set. Metalyzi helps you analyse property investment deals
      faster and smarter — so you can make confident decisions backed by
      real data.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
      <tr>
        <td align="center">
          <a href="${dashboardUrl}"
             class="cta-button"
             style="display:inline-block;background:#ffffff;color:#0f0f0f;font-size:15px;font-weight:700;padding:14px 36px;border-radius:8px;text-decoration:none;letter-spacing:0.2px;">
            Start Analysing
          </a>
        </td>
      </tr>
    </table>
  `)
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

/** Section 2 — Verification email: sent on signup via admin.generateLink */
export function sendVerificationEmail(email: string, verificationUrl: string): Promise<boolean> {
  return sendBrevoEmail(email, "Verify your Metalyzi account", verificationEmailHtml(verificationUrl))
}

/** Section 3 — Welcome email: sent once after email is confirmed */
export function sendWelcomeEmail(email: string): Promise<boolean> {
  return sendBrevoEmail(email, "Welcome to Metalyzi", welcomeEmailHtml())
}

/** Waitlist welcome — DO NOT MODIFY (used by /api/waitlist) */
export function sendWaitlistWelcomeEmail(email: string): Promise<boolean> {
  return sendBrevoEmail(email, "You're on the Metalyzi waitlist!", waitlistEmailHtml())
}

/** Legacy sign-up welcome — kept for backwards compatibility */
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
