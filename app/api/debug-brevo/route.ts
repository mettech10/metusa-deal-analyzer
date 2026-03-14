import { NextResponse } from "next/server"

export async function GET() {
  const brevoApiKey = process.env.BREVO_API_KEY

  if (!brevoApiKey) {
    return NextResponse.json(
      { status: "ERROR", message: "BREVO_API_KEY not set in environment" },
      { status: 500 }
    )
  }

  const testEmail = `test-${Date.now()}@metalyzi.co.uk`

  try {
    console.log("[Brevo Debug] Testing contact creation with:", testEmail)

    const response = await fetch("https://api.brevo.com/v3/contacts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": brevoApiKey,
      },
      body: JSON.stringify({
        email: testEmail,
        updateEnabled: true,
        attributes: {
          WAITLIST: true,
          WAITLIST_DATE: new Date().toISOString().split("T")[0],
          LEAD_SOURCE: "Website Waitlist",
        },
      }),
    })

    const status = response.status
    const bodyText = await response.text()

    let body
    try {
      body = JSON.parse(bodyText)
    } catch {
      body = bodyText
    }

    return NextResponse.json({
      status: status === 201 || status === 204 ? "SUCCESS" : "FAILED",
      create: { status, body },
      keyPrefix: brevoApiKey.substring(0, 15) + "...",
      timestamp: new Date().toISOString(),
    })
  } catch (error) {
    return NextResponse.json(
      {
        status: "ERROR",
        message: error instanceof Error ? error.message : "Unknown error",
        timestamp: new Date().toISOString(),
      },
      { status: 500 }
    )
  }
}
