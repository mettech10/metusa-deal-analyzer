import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// HubSpot API integration
async function addToHubSpot(email: string) {
  const hubspotApiKey = process.env.HUBSPOT_API_KEY

  if (!hubspotApiKey) {
    console.warn("HUBSPOT_API_KEY not configured, skipping HubSpot sync")
    return null
  }

  console.log("[HubSpot] Starting sync for email:", email)
  console.log("[HubSpot] API Key length:", hubspotApiKey.length)

  try {
    // First, try creating with all custom properties
    const response = await fetch(
      `https://api.hubapi.com/crm/v3/objects/contacts`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${hubspotApiKey}`,
        },
        body: JSON.stringify({
          properties: {
            email: email,
            lifecyclestage: "lead",
            lead_source: "Website Waitlist",
            metalyzi_waitlist: "true",
            metalyzi_waitlist_date: new Date().toISOString().split("T")[0], // Date format YYYY-MM-DD
          },
        }),
      }
    )

    console.log("[HubSpot] Create response status:", response.status)
    const responseText = await response.text()
    console.log("[HubSpot] Create response body:", responseText)

    if (response.ok) {
      console.log("[HubSpot] ✓ Successfully created new contact")
      return true
    }

    // Parse error to check if it's a duplicate
    let errorData
    try {
      errorData = JSON.parse(responseText)
    } catch {
      errorData = { message: responseText }
    }

    const isDuplicate = response.status === 409 || 
                       responseText.toLowerCase().includes("duplicate") ||
                       responseText.toLowerCase().includes("already exists") ||
                       errorData?.message?.toLowerCase().includes("already exists")

    // Check if error is due to unknown properties
    const isUnknownProperty = responseText.toLowerCase().includes("unknown property") ||
                              errorData?.message?.toLowerCase().includes("does not exist")

    if (isUnknownProperty) {
      console.log("[HubSpot] ⚠️ Custom properties not found. Trying with basic fields only...")
      
      // Retry without custom properties
      const retryResponse = await fetch(
        `https://api.hubapi.com/crm/v3/objects/contacts`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${hubspotApiKey}`,
          },
          body: JSON.stringify({
            properties: {
              email: email,
              lifecyclestage: "lead",
            },
          }),
        }
      )

      const retryText = await retryResponse.text()
      console.log("[HubSpot] Retry response status:", retryResponse.status)
      console.log("[HubSpot] Retry response body:", retryText)

      if (retryResponse.ok) {
        console.log("[HubSpot] ✓ Contact created (without custom properties - you need to create them in HubSpot)")
        console.log("[HubSpot] Missing properties: metalyzi_waitlist, metalyzi_waitlist_date, lead_source")
        return true
      }
    }

    if (isDuplicate) {
      console.log("[HubSpot] Contact already exists, searching to update...")
      
      // Search for existing contact
      const searchResponse = await fetch(
        `https://api.hubapi.com/crm/v3/objects/contacts/search`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${hubspotApiKey}`,
          },
          body: JSON.stringify({
            filterGroups: [
              {
                filters: [
                  {
                    propertyName: "email",
                    operator: "EQ",
                    value: email,
                  },
                ],
              },
            ],
          }),
        }
      )

      console.log("[HubSpot] Search response status:", searchResponse.status)
      const searchText = await searchResponse.text()
      console.log("[HubSpot] Search response body:", searchText)

      if (searchResponse.ok) {
        const searchData = JSON.parse(searchText)
        if (searchData.results && searchData.results.length > 0) {
          const contactId = searchData.results[0].id
          console.log("[HubSpot] Found existing contact ID:", contactId)

          // Try update with custom properties
          const updateResponse = await fetch(
            `https://api.hubapi.com/crm/v3/objects/contacts/${contactId}`,
            {
              method: "PATCH",
              headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${hubspotApiKey}`,
              },
              body: JSON.stringify({
                properties: {
                  metalyzi_waitlist: "true",
                  metalyzi_waitlist_date: new Date().toISOString().split("T")[0],
                  lead_source: "Website Waitlist",
                },
              }),
            }
          )
          
          console.log("[HubSpot] Update response status:", updateResponse.status)
          const updateText = await updateResponse.text()
          console.log("[HubSpot] Update response body:", updateText)

          if (updateResponse.ok) {
            console.log("[HubSpot] ✓ Successfully updated existing contact")
            return true
          }
          
          // If update failed due to unknown properties, try basic update
          if (updateText.toLowerCase().includes("unknown property")) {
            console.log("[HubSpot] ⚠️ Custom properties not found on update. Skipping them...")
            const basicUpdateResponse = await fetch(
              `https://api.hubapi.com/crm/v3/objects/contacts/${contactId}`,
              {
                method: "PATCH",
                headers: {
                  "Content-Type": "application/json",
                  "Authorization": `Bearer ${hubspotApiKey}`,
                },
                body: JSON.stringify({
                  properties: {
                    lifecyclestage: "lead",
                  },
                }),
              }
            )
            
            if (basicUpdateResponse.ok) {
              console.log("[HubSpot] ✓ Updated existing contact (without custom properties)")
              return true
            }
          }
        } else {
          console.log("[HubSpot] ⚠️ No existing contact found with that email")
        }
      }
    }

    console.error("[HubSpot] ✗ Failed:", response.status, errorData)
    return false
  } catch (error) {
    console.error("[HubSpot] Integration error:", error)
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

    // Add to HubSpot and capture result for better feedback
    let hubspotResult = null
    try {
      hubspotResult = await addToHubSpot(email)
      console.log("[HubSpot] Final result:", hubspotResult)
    } catch (err) {
      console.error("[HubSpot] Sync failed:", err)
    }

    return NextResponse.json(
      { 
        message: "Successfully joined waitlist",
        hubspot: hubspotResult === true ? "synced" : hubspotResult === false ? "failed" : "skipped"
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
