import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// HubSpot API integration
async function addToHubSpot(email: string) {
  const hubspotApiKey = process.env.HUBSPOT_API_KEY

  if (!hubspotApiKey) {
    console.warn("HUBSPOT_API_KEY not configured, skipping HubSpot sync")
    return null
  }

  try {
    // Create or update contact in HubSpot
    const response = await fetch(
      `https://api.hubapi.com/crm/v3/objects/contacts?hapikey=${hubspotApiKey}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
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

    if (!response.ok) {
      // Contact might already exist, try updating instead
      if (response.status === 409) {
        // Search for existing contact and update
        const searchResponse = await fetch(
          `https://api.hubapi.com/crm/v3/objects/contacts/search?hapikey=${hubspotApiKey}`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
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

        if (searchResponse.ok) {
          const searchData = await searchResponse.json()
          if (searchData.results && searchData.results.length > 0) {
            const contactId = searchData.results[0].id

            // Update existing contact
            await fetch(
              `https://api.hubapi.com/crm/v3/objects/contacts/${contactId}?hapikey=${hubspotApiKey}`,
              {
                method: "PATCH",
                headers: {
                  "Content-Type": "application/json",
                },
                body: JSON.stringify({
                  properties: {
                    metalyzi_waitlist: "true",
                    metalyzi_waitlist_date: new Date().toISOString(),
                  },
                }),
              }
            )
          }
        }
      } else {
        console.error("HubSpot API error:", await response.text())
      }
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
