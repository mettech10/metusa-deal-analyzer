import { NextResponse } from "next/server"

export async function GET() {
  const hubspotApiKey = process.env.HUBSPOT_API_KEY
  
  if (!hubspotApiKey) {
    return NextResponse.json(
      { status: "ERROR", message: "HUBSPOT_API_KEY not set in environment" },
      { status: 500 }
    )
  }

  const testEmail = `test-${Date.now()}@metalyzi.co.uk`
  
  try {
    // Test 1: Create contact with all properties
    console.log("[HubSpot Debug] Testing contact creation with:", testEmail)
    
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
            email: testEmail,
            lifecyclestage: "lead",
            lead_source: "Website Waitlist",
            metalyzi_waitlist: "true",
            metalyzi_waitlist_date: new Date().toISOString().split("T")[0],
          },
        }),
      }
    )

    const status = response.status
    const bodyText = await response.text()
    
    let body
    try {
      body = JSON.parse(bodyText)
    } catch {
      body = bodyText
    }

    // If duplicate, try to update
    let updateResult = null
    if (status === 409 || (body?.message && body.message.toLowerCase().includes("already"))) {
      console.log("[HubSpot Debug] Contact exists, testing update flow...")
      
      // Search for contact
      const searchResponse = await fetch(
        `https://api.hubapi.com/crm/v3/objects/contacts/search`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${hubspotApiKey}`,
          },
          body: JSON.stringify({
            filterGroups: [{
              filters: [{
                propertyName: "email",
                operator: "EQ",
                value: testEmail,
              }],
            }],
          }),
        }
      )
      
      const searchBody = await searchResponse.json()
      
      if (searchBody.results && searchBody.results.length > 0) {
        const contactId = searchBody.results[0].id
        
        // Try update
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
              },
            }),
          }
        )
        
        updateResult = {
          status: updateResponse.status,
          body: await updateResponse.text()
        }
      }
    }

    return NextResponse.json({
      status: status === 200 || status === 201 ? "SUCCESS" : "FAILED",
      create: { status, body },
      update: updateResult,
      tokenPrefix: hubspotApiKey.substring(0, 15) + "...",
      timestamp: new Date().toISOString()
    })
    
  } catch (error) {
    return NextResponse.json(
      { 
        status: "ERROR", 
        message: error instanceof Error ? error.message : "Unknown error",
        timestamp: new Date().toISOString()
      },
      { status: 500 }
    )
  }
}
