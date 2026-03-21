"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Plus,
  Trash2,
  Edit2,
  Building2,
  TrendingUp,
  Wallet,
  PoundSterling,
  ArrowLeft,
} from "lucide-react"
import { toast } from "sonner"

interface Property {
  id: string
  address: string
  postcode: string
  property_type: string
  bedrooms: number
  purchase_price: number
  current_value: number
  monthly_rent: number
  mortgage_balance: number
  gross_yield: number
  equity: number
  equity_gain: number
  equity_gain_percent: number
  status: string
  notes: string
  created_at: string
}

interface PortfolioStats {
  total_properties: number
  total_value: number
  total_equity: number
  total_monthly_rent: number
  avg_yield: number
}

export default function PortfolioPage() {
  const [properties, setProperties] = useState<Property[]>([])
  const [stats, setStats] = useState<PortfolioStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)

  useEffect(() => {
    fetchPortfolio()
  }, [])

  async function fetchPortfolio() {
    try {
      const res = await fetch("/api/portfolio")
      if (!res.ok) throw new Error("Failed to fetch")
      const data = await res.json()
      setProperties(data.properties)
      setStats(data.stats)
    } catch (error) {
      toast.error("Failed to load portfolio")
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading portfolio...</div>
      </div>
    )
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
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Portfolio Tracker</h1>
            <p className="mt-1 text-muted-foreground">Track your property investments</p>
          </div>
          <Button onClick={() => setShowAddForm(true)}>
            <Plus className="mr-2 size-4" />
            Add Property
          </Button>
        </div>

        {stats && (
          <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard title="Total Properties" value={stats.total_properties} icon={Building2} />
            <StatCard title="Portfolio Value" value={`£${stats.total_value.toLocaleString()}`} icon={PoundSterling} trend={`£${stats.total_equity.toLocaleString()} equity`} />
            <StatCard title="Monthly Income" value={`£${stats.total_monthly_rent.toLocaleString()}`} icon={Wallet} trend={`£${(stats.total_monthly_rent * 12).toLocaleString()}/year`} />
            <StatCard title="Avg Yield" value={`${stats.avg_yield.toFixed(2)}%`} icon={TrendingUp} />
          </div>
        )}

        {properties.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Building2 className="mx-auto mb-4 size-12 text-muted-foreground" />
            <h3 className="text-lg font-semibold">No properties yet</h3>
            <p className="mt-1 text-muted-foreground">Add your first property to start tracking</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {properties.map((property) => (
              <div key={property.id} className="rounded-xl border border-border bg-card p-4">
                <h3 className="font-semibold">{property.address}</h3>
                <p className="text-sm text-muted-foreground">{property.postcode}</p>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded bg-muted p-2">
                    <p className="text-muted-foreground">Value</p>
                    <p className="font-semibold">£{property.current_value.toLocaleString()}</p>
                  </div>
                  <div className="rounded bg-muted p-2">
                    <p className="text-muted-foreground">Yield</p>
                    <p className="font-semibold">{property.gross_yield.toFixed(2)}%</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

function StatCard({ title, value, icon: Icon, trend }: { title: string; value: string | number; icon: React.ElementType; trend?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="size-5 text-primary" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {trend && <p className="text-xs text-muted-foreground">{trend}</p>}
        </div>
      </div>
    </div>
  )
}