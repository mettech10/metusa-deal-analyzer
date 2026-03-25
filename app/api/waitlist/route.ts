import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"
import { sendWaitlistWelcomeEmail } from "@/lib/brevo-email"

// Brevo API integration
const BREVO_LIST_ID = 3  // Metalyzi Waitlist list

async function addToBrevo(email: string, firstName: string = "") {
  const brevoApiKey = process.env.BREVO_API_KEY

  if (!brevoApiKey) {
    console.warn("BREVO_API_KEY not configured, skipping Brevo sync")
    return null
  }

  console.log("[Brevo] Starting sync for email:", email)

  try {
    // Add contact to Brevo and assign to waitlist list
    const contactRes = await fetch("https://api.brevo.com/v3/contacts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": brevoApiKey,
      },
      body: JSON.stringify({
        email,
        attributes: {
          FIRSTNAME: firstName || "Friend",
          WAITLIST: true,
          WAITLIST_DATE: new Date().toISOString().split("T")[0],
          LEAD_SOURCE: "Website Waitlist",
        },
        listIds: [BREVO_LIST_ID],
        updateEnabled: true,
      }),
    })

    console.log("[Brevo] Contact response status:", contactRes.status)

    if (contactRes.status === 201 || contactRes.status === 204) {
      console.log("[Brevo] ✓ Contact created/updated successfully")
      return true
    }

    const errorText = await contactRes.text()
    console.error("[Brevo] ✗ Failed:", contactRes.status, errorText)
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
      // Email already in waitlist — resend the welcome email in case it was missed
      const emailSent = await sendWaitlistWelcomeEmail(email)
      console.log("[Waitlist] Resent welcome email to existing subscriber:", email, "sent:", emailSent)
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

    // Add to Brevo contacts and send welcome email
    let brevoResult = false
    let emailSent = false
    
    try {
      brevoResult = await addToBrevo(email)
      console.log("[Brevo] Contact result:", brevoResult)
      
      // Send welcome email
      if (brevoResult) {
        console.log("[Brevo] Sending welcome email...")
        emailSent = await sendWaitlistWelcomeEmail(email)
        console.log("[Brevo] Email result:", emailSent)
      }
    } catch (err) {
      console.error("[Brevo] Error:", err)
    }

    return NextResponse.json(
      {
        message: "Successfully joined waitlist",
        brevo: brevoResult ? "synced" : "failed",
        emailSent: emailSent,
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
