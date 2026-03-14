import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// Brevo API integration
const BREVO_API_KEY = process.env.BREVO_API_KEY
const BREVO_LIST_ID = 3  // Metalyzi Waitlist list
const BREVO_TEMPLATE_ID = 1  // Welcome email template

async function addToBrevo(email: string, firstName: string = ""): Promise<{success: boolean, contactAdded: boolean, emailSent: boolean, error?: string}> {
  if (!BREVO_API_KEY) {
    console.error("[Brevo] CRITICAL: BREVO_API_KEY not configured!")
    return { success: false, contactAdded: false, emailSent: false, error: "API key not configured" }
  }

  console.log("[Brevo] ==========================================")
  console.log("[Brevo] Starting sync for email:", email)
  console.log("[Brevo] API Key present:", BREVO_API_KEY.substring(0, 20) + "...")
  console.log("[Brevo] List ID:", BREVO_LIST_ID)
  console.log("[Brevo] Template ID:", BREVO_TEMPLATE_ID)

  let contactAdded = false
  let emailSent = false

  try {
    // 1. Add contact to Brevo and waitlist
    console.log("[Brevo] Step 1: Adding contact to Brevo...")
    const contactRes = await fetch("https://api.brevo.com/v3/contacts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": BREVO_API_KEY,
      },
      body: JSON.stringify({
        email: email,
        attributes: {
          FIRSTNAME: firstName || "Friend",
        },
        listIds: [BREVO_LIST_ID],
        updateEnabled: true,
      }),
    })

    console.log("[Brevo] Contact response status:", contactRes.status)
    
    if (contactRes.status === 201 || contactRes.status === 204) {
      console.log("[Brevo] ✓ Contact added successfully")
      contactAdded = true
    } else {
      const errorText = await contactRes.text()
      console.error("[Brevo] ✗ Contact error:", errorText)
      return { success: false, contactAdded: false, emailSent: false, error: `Contact failed: ${errorText}` }
    }

    // 2. Send welcome email immediately
    console.log("[Brevo] Step 2: Sending welcome email...")
    const emailRes = await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": BREVO_API_KEY,
      },
      body: JSON.stringify({
        to: [{ email: email }],
        templateId: BREVO_TEMPLATE_ID,
      }),
    })

    console.log("[Brevo] Email response status:", emailRes.status)

    if (emailRes.status === 201) {
      const emailData = await emailRes.json()
      console.log("[Brevo] ✓ Welcome email sent successfully, Message ID:", emailData.messageId)
      emailSent = true
    } else {
      const errorText = await emailRes.text()
      console.error("[Brevo] ✗ Email error:", errorText)
      return { success: contactAdded, contactAdded, emailSent: false, error: `Email failed: ${errorText}` }
    }

    console.log("[Brevo] ==========================================")
    return { success: true, contactAdded, emailSent }

  } catch (error) {
    console.error("[Brevo] ✗ CRITICAL ERROR:", error)
    return { success: false, contactAdded, emailSent, error: String(error) }
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

    // Add to Brevo and send welcome email
    console.log("[Waitlist] Starting Brevo integration...")
    let brevoResult = null
    try {
      brevoResult = await addToBrevo(email)
      console.log("[Waitlist] Brevo result:", JSON.stringify(brevoResult, null, 2))
    } catch (err) {
      console.error("[Waitlist] Brevo sync failed:", err)
    }

    return NextResponse.json(
      { 
        message: "Successfully joined waitlist",
        supabase: "saved",
        brevo: brevoResult || { success: false, error: "Not attempted" },
        emailSent: brevoResult?.emailSent || false
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
