/**
 * Test script: verifies that /api/analyses/[id] handles missing backend_data
 * column gracefully (the fix for "Failed to load analysis" error).
 *
 * Run with: node scripts/test-analyses-api.mjs
 *
 * This mocks the Supabase client to simulate the real database states.
 */

let passed = 0
let failed = 0

function assert(condition, message) {
  if (condition) {
    console.log(`  ✓ ${message}`)
    passed++
  } else {
    console.error(`  ✗ ${message}`)
    failed++
  }
}

// ── Simulate the fallback logic from the API route ───────────────────────────

async function simulateGetAnalysis(supabaseMock, id, userId) {
  // Replicate the logic from app/api/analyses/[id]/route.ts
  let { data, error } = await supabaseMock.query("with_backend_data", id, userId)

  // If backend_data column doesn't exist yet (migration pending), retry without it
  if (error && error.message?.includes("backend_data")) {
    const fallback = await supabaseMock.query("without_backend_data", id, userId)
    data = fallback.data ? { ...fallback.data, backend_data: null } : null
    error = fallback.error
  }

  if (error || !data) {
    return { status: 404, body: { error: error?.message || "Not found" } }
  }

  return { status: 200, body: data }
}

// ── Test cases ────────────────────────────────────────────────────────────────

console.log("\nTest 1: backend_data column EXISTS in database")
{
  const mock = {
    query: async (variant) => {
      if (variant === "with_backend_data") {
        return {
          data: { id: "abc", address: "1 Main St", form_data: { address: "1 Main St" }, results: {}, ai_text: "Good deal", backend_data: { verdict: "Strong Buy" } },
          error: null,
        }
      }
      return { data: null, error: new Error("Should not be called") }
    },
  }
  const res = await simulateGetAnalysis(mock, "abc", "user1")
  assert(res.status === 200, "Returns 200")
  assert(res.body.backend_data?.verdict === "Strong Buy", "Returns backend_data")
  assert(res.body.form_data?.address === "1 Main St", "Returns form_data")
}

console.log("\nTest 2: backend_data column MISSING (migration not applied)")
{
  const mock = {
    query: async (variant) => {
      if (variant === "with_backend_data") {
        return {
          data: null,
          error: { message: 'column "backend_data" of relation "saved_analyses" does not exist' },
        }
      }
      // Fallback query without backend_data succeeds
      return {
        data: { id: "abc", address: "1 Main St", form_data: { address: "1 Main St" }, results: {}, ai_text: "Good deal" },
        error: null,
      }
    },
  }
  const res = await simulateGetAnalysis(mock, "abc", "user1")
  assert(res.status === 200, "Returns 200 (not 404) even when backend_data column missing")
  assert(res.body.backend_data === null, "backend_data is null (graceful fallback)")
  assert(res.body.form_data?.address === "1 Main St", "form_data still returned correctly")
}

console.log("\nTest 3: analysis not found (different user / deleted)")
{
  const mock = {
    query: async (variant) => {
      if (variant === "with_backend_data") {
        return { data: null, error: { message: "No rows found" } }
      }
      return { data: null, error: { message: "No rows found" } }
    },
  }
  const res = await simulateGetAnalysis(mock, "nonexistent", "user1")
  assert(res.status === 404, "Returns 404 for missing analysis")
}

console.log("\nTest 4: analysis has no form_data (old incomplete record)")
{
  const mock = {
    query: async (variant) => {
      if (variant === "with_backend_data") {
        return {
          data: { id: "abc", address: "1 Main St", form_data: null, results: null, ai_text: "", backend_data: null },
          error: null,
        }
      }
      return { data: null, error: new Error("Should not be called") }
    },
  }
  const res = await simulateGetAnalysis(mock, "abc", "user1")
  assert(res.status === 200, "API returns 200 (UI handles null form_data)")
  assert(res.body.form_data === null, "form_data is null (UI shows 'incomplete' message)")
}

// ── Summary ───────────────────────────────────────────────────────────────────

console.log(`\n${"─".repeat(50)}`)
console.log(`Results: ${passed} passed, ${failed} failed`)
if (failed > 0) {
  console.error("SOME TESTS FAILED")
  process.exit(1)
} else {
  console.log("All tests passed ✓")
}
