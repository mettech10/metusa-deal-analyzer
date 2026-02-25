import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// HubSpot API integration
async function addToHubSpot(email: string) {
  const hubspotApiKey = process.env.HUBSPOT_API_KEY

  if (!hubspotApiKey) {
    console.warn("HUBSPOT_API_KEY not configured, skipping HubSpot sync")
    return null
  }

  console.log("Starting HubSpot sync for email:", email)
  console.log("API Key present (first 10 chars):", hubspotApiKey.substring(0, 10) + "...")

  try {
    // Try the newer Private App / Access Token method first
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
            metalyzi_waitlist_date: new Date().toISOString(),
          },
        }),
      }
    )

    console.log("HubSpot create response status:", response.status)
    const responseText = await response.text()
    console.log("HubSpot create response body:", responseText)

    if (!response.ok) {
      // If 409 (conflict) or 400 with "duplicate" error, try updating
      const isDuplicate = response.status === 409 || 
                         responseText.toLowerCase().includes("duplicate") ||
                         responseText.toLowerCase().includes("already exists")
      
      if (isDuplicate) {
        console.log("Contact already exists, searching to update...")
        
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

        console.log("HubSpot search response status:", searchResponse.status)
        const searchText = await searchResponse.text()
        console.log("HubSpot search response body:", searchText)

        if (searchResponse.ok) {
          const searchData = JSON.parse(searchText)
          if (searchData.results && searchData.results.length > 0) {
            const contactId = searchData.results[0].id
            console.log("Found existing contact, updating ID:", contactId)

            // Update existing contact
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
                    metalyzi_waitlist_date: new Date().toISOString(),
                  },
                }),
              }
            )
            
            console.log("HubSpot update response status:", updateResponse.status)
            const updateText = await updateResponse.text()
            console.log("HubSpot update response body:", updateText)
          } else {
            console.log("No existing contact found with that email")
          }
        }
      } else {
        console.error("HubSpot API error:", response.status, responseText)
      }
    } else {
      console.log("Successfully created new contact in HubSpot")
    }

    return true
  } catch (error) {
    console.error("HubSpot integration error:", error)
    return null
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

    // Add to HubSpot (non-blocking)
    addToHubSpot(email).catch((err) => {
      console.error("HubSpot sync failed:", err)
    })

    return NextResponse.json(
      { message: "Successfully joined waitlist" },
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
