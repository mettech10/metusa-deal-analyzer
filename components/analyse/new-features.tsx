"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

// Regional Benchmark Card Component
function RegionalBenchmarkCard({
  benchmark,
  actualYield,
  actualCashflow,
}: {
  benchmark?: any
  actualYield: number
  actualCashflow: number
}) {
  if (!benchmark) return null

  const { area, deal_type, btl_median_yield, hmo_median_yield, median_cashflow } = benchmark
  const medianYield = deal_type === "HMO" ? hmo_median_yield : btl_median_yield

  const yieldDiff = actualYield - medianYield
  const cashflowDiff = actualCashflow - median_cashflow

  const yieldBetter = yieldDiff > 0
  const cashflowBetter = cashflowDiff > 0

  return (
    <Card className="border-primary/20">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🎯</span>
          <CardTitle className="text-sm">Regional Benchmark: {area}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg bg-muted/50 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Gross Yield</span>
              <span className={`text-xs font-medium ${yieldBetter ? 'text-success' : 'text-destructive'}`}>
                {yieldBetter ? "+" : ""}{yieldDiff.toFixed(1)}%
              </span>
            </div>
            <div className="mt-2 flex items-end gap-2">
              <span className="text-2xl font-bold">{actualYield.toFixed(1)}%</span>
              <span className="text-xs text-muted-foreground">vs {medianYield}% avg</span>
            </div>
          </div>

          <div className="rounded-lg bg-muted/50 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Monthly Cashflow</span>
              <span className={`text-xs font-medium ${cashflowBetter ? 'text-success' : 'text-destructive'}`}>
                {cashflowBetter ? "+" : ""}£{cashflowDiff.toFixed(0)}
              </span>
            </div>
            <div className="mt-2 flex items-end gap-2">
              <span className="text-2xl font-bold">£{actualCashflow.toFixed(0)}</span>
              <span className="text-xs text-muted-foreground">vs £{median_cashflow} avg</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Risk Flags Dashboard Component
function RiskFlagsDashboard({ flags }: { flags?: any[] }) {
  if (!flags || flags.length === 0) {
    return null
  }

  const highRisks = flags.filter((f) => f.severity === "HIGH")
  const mediumRisks = flags.filter((f) => f.severity === "MEDIUM")

  return (
    <Card className={highRisks.length > 0 ? "border-destructive/30" : "border-warning/30"}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">⚠️ Risk Assessment</CardTitle>
          <div className="flex gap-2">
            {highRisks.length > 0 && (
              <span className="text-xs bg-destructive text-white px-2 py-1 rounded">{highRisks.length} High</span>
            )}
            {mediumRisks.length > 0 && (
              <span className="text-xs bg-warning text-black px-2 py-1 rounded">{mediumRisks.length} Medium</span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-3">
          {flags.map((flag: any) => (
            <div
              key={flag.id}
              className={`rounded-lg border p-3 ${
                flag.severity === "HIGH"
                  ? "border-destructive/30 bg-destructive/5"
                  : flag.severity === "MEDIUM"
                  ? "border-warning/30 bg-warning/5"
                  : "border-border bg-muted/20"
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{flag.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      flag.severity === "HIGH" ? "bg-destructive text-white" : 
                      flag.severity === "MEDIUM" ? "bg-warning text-black" : 
                      "bg-muted"
                    }`}>
                      {flag.severity}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{flag.description}</p>
                  <p className="mt-2 text-xs"><strong>Mitigation:</strong> {flag.mitigation}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// Sensitivity Analysis Panel Component
function SensitivityAnalysisPanel({ data, backendData }: { data: any, backendData?: any }) {
  const [scenario, setScenario] = useState({
    mortgageRate: data.interestRate || 5.5,
    monthlyRent: data.monthlyRent || 1000,
    vacancyRate: 4.2,
  })

  return (
    <Card className="border-primary/20">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">🎚️ Sensitivity Analysis</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-3 mb-4">
          <div className="rounded-lg bg-muted/30 p-3">
            <label className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Mortgage Rate</span>
              <span className="font-semibold">{scenario.mortgageRate.toFixed(1)}%</span>
            </label>
            <input
              type="range"
              min="0.5"
              max="10"
              step="0.25"
              value={scenario.mortgageRate}
              onChange={(e) => setScenario({...scenario, mortgageRate: parseFloat(e.target.value)})}
              className="mt-2 w-full"
            />
          </div>

          <div className="rounded-lg bg-muted/30 p-3">
            <label className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Monthly Rent</span>
              <span className="font-semibold">£{scenario.monthlyRent.toFixed(0)}</span>
            </label>
            <input
              type="range"
              min="500"
              max={Math.max((data.monthlyRent || 1000) * 2, 3000)}
              step="50"
              value={scenario.monthlyRent}
              onChange={(e) => setScenario({...scenario, monthlyRent: parseFloat(e.target.value)})}
              className="mt-2 w-full"
            />
          </div>

          <div className="rounded-lg bg-muted/30 p-3">
            <label className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Vacancy Rate</span>
              <span className="font-semibold">{scenario.vacancyRate.toFixed(1)}%</span>
            </label>
            <input
              type="range"
              min="0"
              max="20"
              step="0.5"
              value={scenario.vacancyRate}
              onChange={(e) => setScenario({...scenario, vacancyRate: parseFloat(e.target.value)})}
              className="mt-2 w-full"
            />
          </div>
        </div>

        <div className="text-xs text-muted-foreground text-center">
          Adjust sliders to see how changes affect your deal (live calculation coming soon)
        </div>
      </CardContent>
    </Card>
  )
}
export { RegionalBenchmarkCard, RiskFlagsDashboard, SensitivityAnalysisPanel }
