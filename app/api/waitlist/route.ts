import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"
import { sendWaitlistWelcomeEmail } from "@/lib/brevo-email"

// Brevo API integration
async function addToBrevo(email: string) {
  const brevoApiKey = process.env.BREVO_API_KEY

  if (!brevoApiKey) {
    console.warn("BREVO_API_KEY not configured, skipping Brevo sync")
    return null
  }

  console.log("[Brevo] Starting sync for email:", email)

  try {
    const response = await fetch("https://api.brevo.com/v3/contacts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": brevoApiKey,
      },
      body: JSON.stringify({
        email,
        updateEnabled: true,
        attributes: {
          WAITLIST: true,
          WAITLIST_DATE: new Date().toISOString().split("T")[0],
          LEAD_SOURCE: "Website Waitlist",
        },
      }),
    })

    console.log("[Brevo] Response status:", response.status)

    if (response.status === 201 || response.status === 204) {
      console.log("[Brevo] ✓ Contact created/updated successfully")
      return true
    }

    const body = await response.text()
    console.error("[Brevo] ✗ Failed:", response.status, body)
    return false
  } catch (error) {
    console.error("[Brevo] Integration error:", error)
    return false
  }
}

export async function POST(request: Request) {
  try {
    const { email } = await request.json()

    if (!email || !email.includes("@")) {
      return NextResponse.json(
        { error: "Valid email required" },
        { status: 400 }
      )
    }

    const supabase = await createClient()

    // Check if email already exists
    const { data: existing } = await supabase
      .from("waitlist")
      .select("email")
      .eq("email", email)
      .single()

    if (existing) {
      return NextResponse.json(
        { message: "Already on waitlist" },
        { status: 200 }
      )
    }

    // Insert new email into Supabase
    const { error } = await supabase.from("waitlist").insert({
      email,
      created_at: new Date().toISOString(),
    })

    if (error) {
      console.error("Waitlist insert error:", error)
      return NextResponse.json(
        { error: "Failed to join waitlist" },
        { status: 500 }
      )
    }

    // Add to Brevo contacts and send welcome email (fire-and-forget)
    let brevoResult = null
    try {
      brevoResult = await addToBrevo(email)
      console.log("[Brevo] Final result:", brevoResult)
    } catch (err) {
      console.error("[Brevo] Sync failed:", err)
    }
    sendWaitlistWelcomeEmail(email).catch(console.error)

    return NextResponse.json(
      {
        message: "Successfully joined waitlist",
        brevo: brevoResult === true ? "synced" : brevoResult === false ? "failed" : "skipped",
      },
      { status: 201 }
    )
  } catch (error) {
    console.error("Waitlist API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}
