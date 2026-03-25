"use client"

import { useState } from "react"
import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ArrowLeft, Scale, Plus, Trash2, BarChart3 } from "lucide-react"
import { toast } from "sonner"

interface Deal {
  id: string
  address: string
  price: number
  monthly_rent: number
  gross_yield: number
  monthly_cashflow: number
  roi: number
  deal_score: number
  verdict: string
}

export default function ComparePage() {
  const [deals, setDeals] = useState<Deal[]>([])
  const [comparison, setComparison] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const addDeal = () => {
    const newDeal: Deal = {
      id: Date.now().toString(),
      address: "",
      price: 0,
      monthly_rent: 0,
      gross_yield: 0,
      monthly_cashflow: 0,
      roi: 0,
      deal_score: 0,
      verdict: "HOLD",
    }
    setDeals([...deals, newDeal])
  }

  const removeDeal = (id: string) => {
    setDeals(deals.filter((d) => d.id !== id))
  }

  const updateDeal = (id: string, field: keyof Deal, value: any) => {
    setDeals(deals.map((d) => (d.id === id ? { ...d, [field]: value } : d)))
  }

  const runComparison = async () => {
    if (deals.length < 2) {
      toast.error("Add at least 2 deals to compare")
      return
    }

    setLoading(true)
    try {
      const res = await fetch("/api/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deals }),
      })

      if (!res.ok) throw new Error("Failed to compare")

      const data = await res.json()
      setComparison(data.comparison)
      toast.success("Comparison complete!")
    } catch (error) {
      toast.error("Failed to compare deals")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <Link href="/?dev=metalyzi2026" className="flex items-center gap-2.5">
            <Image src="/logo.png" alt="Metalyzi" width={32} height={32} className="rounded-lg" />
            <span className="text-lg font-semibold">Metalyzi</span>
          </Link>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/?dev=metalyzi2026">
              <ArrowLeft className="mr-2 size-4" />
              Back
            </Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Deal Comparison</h1>
          <p className="mt-1 text-muted-foreground">Compare up to 5 deals side-by-side</p>
        </div>

        <div className="mb-6 flex gap-2">
          <Button onClick={addDeal} disabled={deals.length >= 5}>
            <Plus className="mr-2 size-4" />
            Add Deal ({deals.length}/5)
          </Button>
          <Button onClick={runComparison} disabled={deals.length < 2 || loading}>
            <Scale className="mr-2 size-4" />
            {loading ? "Comparing..." : "Compare Deals"}
          </Button>
        </div>

        {deals.length > 0 && (
          <div className="mb-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {deals.map((deal, index) => (
              <div key={deal.id} className="rounded-xl border border-border bg-card p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="font-semibold">Deal {index + 1}</span>
                  <Button variant="ghost" size="icon" className="size-8" onClick={() => removeDeal(deal.id)}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="text-sm text-muted-foreground">Address</label>
                    <Input
                      value={deal.address}
                      onChange={(e) => updateDeal(deal.id, "address", e.target.value)}
                      placeholder="Property address"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-sm text-muted-foreground">Price (£)</label>
                      <Input
                        type="number"
                        value={deal.price || ""}
                        onChange={(e) => updateDeal(deal.id, "price", Number(e.target.value))}
                        placeholder="200000"
                      />
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">Monthly Rent (£)</label>
                      <Input
                        type="number"
                        value={deal.monthly_rent || ""}
                        onChange={(e) => updateDeal(deal.id, "monthly_rent", Number(e.target.value))}
                        placeholder="1200"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-sm text-muted-foreground">Yield (%)</label>
                      <Input
                        type="number"
                        step="0.1"
                        value={deal.gross_yield || ""}
                        onChange={(e) => updateDeal(deal.id, "gross_yield", Number(e.target.value))}
                        placeholder="7.2"
                      />
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">Cashflow (£)</label>
                      <Input
                        type="number"
                        value={deal.monthly_cashflow || ""}
                        onChange={(e) => updateDeal(deal.id, "monthly_cashflow", Number(e.target.value))}
                        placeholder="400"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-sm text-muted-foreground">ROI (%)</label>
                      <Input
                        type="number"
                        step="0.1"
                        value={deal.roi || ""}
                        onChange={(e) => updateDeal(deal.id, "roi", Number(e.target.value))}
                        placeholder="18.5"
                      />
                    </div>
                    <div>
                      <label className="text-sm text-muted-foreground">Score (0-100)</label>
                      <Input
                        type="number"
                        value={deal.deal_score || ""}
                        onChange={(e) => updateDeal(deal.id, "deal_score", Number(e.target.value))}
                        placeholder="85"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-sm text-muted-foreground">Verdict</label>
                    <select
                      value={deal.verdict}
                      onChange={(e) => updateDeal(deal.id, "verdict", e.target.value)}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2"
                    >
                      <option value="PROCEED">PROCEED</option>
                      <option value="REVIEW">REVIEW</option>
                      <option value="HOLD">HOLD</option>
                      <option value="AVOID">AVOID</option>
                    </select>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {comparison && (
          <div className="rounded-xl border border-border bg-card p-6">
            <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold">
              <BarChart3 className="size-5" />
              Comparison Results
            </h2>

            {comparison.best && (
              <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-lg bg-primary/10 p-4">
                  <p className="text-sm text-muted-foreground">Best Yield</p>
                  <p className="text-lg font-bold">{comparison.best.yield.deal}</p>
                  <p className="text-2xl font-bold text-primary">{comparison.best.yield.value}%</p>
                </div>
                <div className="rounded-lg bg-primary/10 p-4">
                  <p className="text-sm text-muted-foreground">Best Cashflow</p>
                  <p className="text-lg font-bold">{comparison.best.cashflow.deal}</p>
                  <p className="text-2xl font-bold text-primary">£{comparison.best.cashflow.value}</p>
                </div>
                <div className="rounded-lg bg-primary/10 p-4">
                  <p className="text-sm text-muted-foreground">Best ROI</p>
                  <p className="text-lg font-bold">{comparison.best.roi.deal}</p>
                  <p className="text-2xl font-bold text-primary">{comparison.best.roi.value}%</p>
                </div>
                <div className="rounded-lg bg-primary/10 p-4">
                  <p className="text-sm text-muted-foreground">Best Score</p>
                  <p className="text-lg font-bold">{comparison.best.score.deal}</p>
                  <p className="text-2xl font-bold text-primary">{comparison.best.score.value}/100</p>
                </div>
              </div>
            )}

            {comparison.rankings && (
              <div>
                <h3 className="mb-3 font-semibold">Rankings</h3>
                <div className="space-y-2">
                  {comparison.rankings.map((deal: any, index: number) => (
                    <div
                      key={index}
                      className="flex items-center justify-between rounded-lg border border-border p-3"
                    >
                      <div className="flex items-center gap-3">
                        <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 font-bold">
                          {index + 1}
                        </span>
                        <div>
                          <p className="font-medium">{deal.address || `Deal ${index + 1}`}</p>
                          <p className="text-sm text-muted-foreground">
                            Score: {deal.score} | Yield: {deal.yield}%
                          </p>
                        </div>
                      </div>
                      <span
                        className={`rounded-full px-3 py-1 text-sm font-medium ${
                          deal.verdict === "PROCEED"
                            ? "bg-green-100 text-green-800"
                            : deal.verdict === "AVOID"
                            ? "bg-red-100 text-red-800"
                            : "bg-yellow-100 text-yellow-800"
                        }`}
                      >
                        {deal.verdict}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}