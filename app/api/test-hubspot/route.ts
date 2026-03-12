import { NextResponse } from "next/server"

export async function GET() {
  const hubspotApiKey = process.env.HUBSPOT_API_KEY
  
  if (!hubspotApiKey) {
    return NextResponse.json({
      status: "ERROR",
      message: "HUBSPOT_API_KEY not found in environment variables",
      hint: "Add HUBSPOT_API_KEY to Vercel environment variables"
    }, { status: 500 })
  }
  
  // Test the API key with a simple request
  try {
    const testResponse = await fetch(
      "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
      {
        headers: {
          "Authorization": `Bearer ${hubspotApiKey}`,
        },
      }
    )
    
    if (testResponse.ok) {
      const data = await testResponse.json()
      return NextResponse.json({
        status: "SUCCESS",
        message: "HubSpot API connection working",
        keyPrefix: hubspotApiKey.substring(0, 15) + "...",
        totalContacts: data.total,
        hint: "Your API key is valid. If contacts aren't syncing, check the waitlist API logs."
      })
    } else {
      const errorText = await testResponse.text()
      return NextResponse.json({
        status: "ERROR",
        message: "HubSpot API returned error",
        httpStatus: testResponse.status,
        errorDetails: errorText,
        keyPrefix: hubspotApiKey.substring(0, 15) + "...",
        hint: testResponse.status === 401 
          ? "Your API key is invalid or expired. Get a new one from HubSpot Settings > Private Apps"
          : "Check the error details above"
      }, { status: 500 })
    }
  } catch (error) {
    return NextResponse.json({
      status: "ERROR",
      message: "Failed to connect to HubSpot API",
      error: error instanceof Error ? error.message : String(error),
      hint: "Network error or HubSpot API is down"
    }, { status: 500 })
  }
}
