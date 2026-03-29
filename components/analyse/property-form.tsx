"use client"

import { useEffect } from "react"
import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2, Link2, Info } from "lucide-react"
import type { PropertyFormData, PropertyTypeDetail, TenureType } from "@/lib/types"
import { estimateRefurbCost } from "@/lib/calculations"

const schema = z.object({
  address: z.string().min(1, "Address is required"),
  postcode: z.string().min(1, "Postcode is required"),
  purchasePrice: z.coerce.number().min(0),
  propertyType: z.enum(["house", "flat", "commercial"]),
  propertyTypeDetail: z.enum([
    "terraced", "semi-detached", "detached", "end-of-terrace",
    "flat-apartment", "bungalow", "maisonette", "other",
  ]).optional(),
  tenureType: z.enum(["freehold", "leasehold"]).optional(),
  leaseYears: z.coerce.number().min(1).max(999).optional(),
  investmentType: z.enum(["btl", "brr", "hmo", "flip", "r2sa", "development"]),
  sqft: z.coerce.number().min(0).optional(),
  bedrooms: z.coerce.number().min(0).max(20),
  condition: z.enum(["excellent", "good", "fair", "needs-work"]),
  buyerType: z.enum(["first-time", "additional"]),
  refurbishmentBudget: z.coerce.number().min(0),
  legalFees: z.coerce.number().min(0),
  surveyCosts: z.coerce.number().min(0),
  purchaseType: z.enum(["mortgage", "bridging-loan", "cash"]),
  depositPercentage: z.coerce.number().min(0).max(100),
  interestRate: z.coerce.number().min(0).max(20),
  mortgageTerm: z.coerce.number().min(1).max(40),
  mortgageType: z.enum(["repayment", "interest-only"]).optional().default("interest-only"),
  // Bridging loan fields
  bridgingMonthlyRate: z.coerce.number().min(0).max(5).optional(),
  bridgingTermMonths: z.coerce.number().min(1).max(36).optional(),
  bridgingArrangementFee: z.coerce.number().min(0).max(5).optional(),
  bridgingExitFee: z.coerce.number().min(0).max(5).optional(),
  // BRR / Flip
  arv: z.coerce.number().min(0).optional(),
  // HMO
  roomCount: z.coerce.number().min(0).max(20).optional(),
  avgRoomRate: z.coerce.number().min(0).optional(),
  // R2SA
  saMonthlySARevenue: z.coerce.number().min(0).optional(),
  saSetupCosts: z.coerce.number().min(0).optional(),
  capitalGrowthRate: z.coerce.number().min(0).max(30).optional(),
  monthlyRent: z.coerce.number().min(0),
  annualRentIncrease: z.coerce.number().min(0).max(20),
  voidWeeks: z.coerce.number().min(0).max(52),
  managementFeePercent: z.coerce.number().min(0).max(100),
  insurance: z.coerce.number().min(0),
  maintenance: z.coerce.number().min(0),
  groundRent: z.coerce.number().min(0),
  bills: z.coerce.number().min(0),
})

interface PropertyFormProps {
  onSubmit: (data: PropertyFormData) => void
  isLoading: boolean
  defaultValues?: Partial<PropertyFormData>
  prefilled?: boolean
}

function FormField({
  label,
  error,
  children,
  hint,
}: {
  label: string
  error?: string
  children: React.ReactNode
  hint?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-sm text-foreground">{label}</Label>
      {children}
      {hint && !error && (
        <span className="text-xs text-muted-foreground">{hint}</span>
      )}
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  )
}

export function PropertyForm({ onSubmit, isLoading, defaultValues, prefilled }: PropertyFormProps) {
  const baseDefaults: PropertyFormData = {
    address: "",
    postcode: "",
    purchasePrice: 0,
    propertyType: "house",
    investmentType: "btl",
    sqft: undefined,
    bedrooms: 3,
    condition: "good",
    buyerType: "additional",
    refurbishmentBudget: 0,
    legalFees: 1500,
    surveyCosts: 500,
    purchaseType: "mortgage",
    depositPercentage: 25,
    interestRate: 5.5,
    mortgageTerm: 25,
    mortgageType: "interest-only",
    bridgingMonthlyRate: 0.75,
    bridgingTermMonths: 12,
    bridgingArrangementFee: 1.0,
    bridgingExitFee: 0.5,
    capitalGrowthRate: 4,
    arv: 0,
    roomCount: 0,
    avgRoomRate: 0,
    saMonthlySARevenue: 0,
    saSetupCosts: 5000,
    monthlyRent: 0,
    annualRentIncrease: 2,
    voidWeeks: 2,
    managementFeePercent: 10,
    insurance: 300,
    maintenance: 500,
    groundRent: 0,
    bills: 0,
  }

  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    formState: { errors },
  } = useForm<PropertyFormData>({
    resolver: zodResolver(schema),
    defaultValues: { ...baseDefaults, ...defaultValues },
  })

  const purchaseType = watch("purchaseType")
  const investmentType = watch("investmentType")
  const sqftValue = watch("sqft")
  const conditionValue = watch("condition")
  const propertyTypeValue = watch("propertyType")
  const postcodeValue = watch("postcode")
  const refurbValue = watch("refurbishmentBudget")
  const tenureTypeValue = watch("tenureType")
  const propertyTypeDetailValue = watch("propertyTypeDetail")

  // Auto-map the granular property type to the broad type used by calculations.
  useEffect(() => {
    if (!propertyTypeDetailValue) return
    const flatTypes = ["flat-apartment", "maisonette"]
    const broad = flatTypes.includes(propertyTypeDetailValue) ? "flat" : "house"
    setValue("propertyType", broad, { shouldDirty: false })
  }, [propertyTypeDetailValue, setValue])

  // Auto-compute refurb budget from sqm + condition whenever they change,
  // but only if the user hasn't manually entered a custom refurb amount
  // (i.e. refurb is still 0 or matches our last auto-estimate).
  useEffect(() => {
    if (!sqftValue || sqftValue <= 0) return
    const estimated = estimateRefurbCost(sqftValue, conditionValue, propertyTypeValue, postcodeValue)
    // Only overwrite if field is currently 0 or if estimate changed meaningfully
    if (refurbValue === 0 || refurbValue === undefined) {
      setValue("refurbishmentBudget", estimated, { shouldDirty: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sqftValue, conditionValue, propertyTypeValue, postcodeValue])

  const isR2SA     = investmentType === "r2sa"
  const isHMO      = investmentType === "hmo"
  const isBRR      = investmentType === "brr"
  const isFLIP     = investmentType === "flip"
  const isBridging = purchaseType === "bridging-loan"
  const isCash     = purchaseType === "cash"

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-8">
      {/* URL Pre-fill Banner */}
      {prefilled && (
        <div className="flex items-start gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
          <Link2 className="mt-0.5 size-4 shrink-0 text-primary" />
          <div className="flex flex-col gap-0.5">
            <p className="text-sm font-medium text-foreground">
              Property details imported from listing
            </p>
            <p className="text-xs text-muted-foreground">
              We pre-filled what we could from the URL. Please review the details above and fill in the remaining fields below (rent, financing, running costs) to get a full analysis.
            </p>
          </div>
        </div>
      )}

      {/* ── Property Details ─────────────────────────────────────────── */}
      <div className="flex flex-col gap-4">
        <h3 className="text-base font-semibold text-foreground">Property Details</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <FormField label="Property Address" error={errors.address?.message}>
              <Input
                placeholder="e.g. 10 Downing Street, London"
                {...register("address")}
              />
            </FormField>
          </div>
          <FormField label="Postcode" error={errors.postcode?.message}>
            <Input placeholder="e.g. SW1A 2AA" {...register("postcode")} />
          </FormField>
          {/* Investment Strategy */}
          <FormField label="Investment Strategy">
            <Controller
              control={control}
              name="investmentType"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="btl">Buy-to-Let (BTL) — Long-term rental</SelectItem>
                    <SelectItem value="hmo">HMO — Room-by-room rental</SelectItem>
                    <SelectItem value="brr">Buy, Refurb &amp; Refinance (BRR)</SelectItem>
                    <SelectItem value="flip">Flip / Renovation — Buy &amp; sell</SelectItem>
                    <SelectItem value="r2sa">Rent-to-SA (R2SA) — Sublet as SA</SelectItem>
                    <SelectItem value="development">Development</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </FormField>
          {/* Purchase Price — hidden for R2SA (no purchase) */}
          {!isR2SA && (
            <FormField label="Purchase Price" error={errors.purchasePrice?.message}>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input
                  type="number"
                  className="pl-7"
                  placeholder="250000"
                  {...register("purchasePrice")}
                />
              </div>
            </FormField>
          )}
          <FormField label="Property Type">
            <Controller
              control={control}
              name="propertyTypeDetail"
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={(v) => field.onChange(v as PropertyTypeDetail)}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="terraced">Terraced</SelectItem>
                    <SelectItem value="semi-detached">Semi-Detached</SelectItem>
                    <SelectItem value="detached">Detached</SelectItem>
                    <SelectItem value="end-of-terrace">End of Terrace</SelectItem>
                    <SelectItem value="flat-apartment">Flat / Apartment</SelectItem>
                    <SelectItem value="bungalow">Bungalow</SelectItem>
                    <SelectItem value="maisonette">Maisonette</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </FormField>
          <FormField label="Tenure Type">
            <Controller
              control={control}
              name="tenureType"
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={(v) => field.onChange(v as TenureType)}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select tenure" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="freehold">Freehold</SelectItem>
                    <SelectItem value="leasehold">Leasehold</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </FormField>
          {tenureTypeValue === "leasehold" && (
            <FormField label="Lease Years Remaining" hint="Years left on the lease">
              <Input
                type="number"
                placeholder="e.g. 125"
                {...register("leaseYears")}
              />
            </FormField>
          )}
          <FormField label="Floor Size (sqft)" hint="From listing or EPC certificate (optional)">
            <div className="relative">
              <Input
                type="number"
                className="pr-14"
                placeholder="990"
                {...register("sqft")}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">sqft</span>
            </div>
          </FormField>
          <FormField label="Bedrooms">
            <Input type="number" {...register("bedrooms")} />
          </FormField>
          <FormField label="Condition">
            <Controller
              control={control}
              name="condition"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="excellent">Excellent</SelectItem>
                    <SelectItem value="good">Good</SelectItem>
                    <SelectItem value="fair">Fair</SelectItem>
                    <SelectItem value="needs-work">Needs Work</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </FormField>
        </div>
      </div>

      {/* ── Purchase Costs (hidden for R2SA — no purchase) ───────────── */}
      {!isR2SA && (
        <div className="flex flex-col gap-4">
          <h3 className="text-base font-semibold text-foreground">Purchase Costs</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <FormField label="Buyer Type" hint="Affects Stamp Duty Land Tax (SDLT) calculation">
                <Controller
                  control={control}
                  name="buyerType"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="additional">Second Home / Investment (5% SDLT surcharge)</SelectItem>
                        <SelectItem value="first-time">First-Time Buyer (0% up to £425k, 5% on £425k–£625k)</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
              </FormField>
            </div>
            <FormField label="Refurbishment Budget" hint={sqftValue ? "Auto-estimated from size & condition — edit to override" : "Enter manually or set floor size + condition above"}>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input type="number" className="pl-7" {...register("refurbishmentBudget")} />
              </div>
            </FormField>
            <FormField label="Legal Fees">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input type="number" className="pl-7" {...register("legalFees")} />
              </div>
            </FormField>
            <FormField label="Survey Costs">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input type="number" className="pl-7" {...register("surveyCosts")} />
              </div>
            </FormField>
            {/* ARV — shown for BRR and Flip */}
            {(isBRR || isFLIP) && (
              <FormField label="After Repair Value (ARV)" hint="Expected value after renovation">
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                  <Input
                    type="number"
                    className="pl-7"
                    placeholder="220000"
                    {...register("arv")}
                  />
                </div>
              </FormField>
            )}
          </div>
        </div>
      )}

      {/* ── Financing (hidden for R2SA) ───────────────────────────────── */}
      {!isR2SA && (
        <div className="flex flex-col gap-4">
          <h3 className="text-base font-semibold text-foreground">Financing</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Purchase Type">
              <Controller
                control={control}
                name="purchaseType"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mortgage">Mortgage</SelectItem>
                      <SelectItem value="bridging-loan">Bridging Loan</SelectItem>
                      <SelectItem value="cash">Cash</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </FormField>
            {/* Deposit — shown for mortgage and bridging (not cash) */}
            {!isCash && (
              <FormField label="Deposit" hint="% of purchase price">
                <div className="relative">
                  <Input
                    type="number"
                    step="0.5"
                    className="pr-7"
                    {...register("depositPercentage")}
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                </div>
              </FormField>
            )}
            {/* Mortgage-specific fields */}
            {!isCash && !isBridging && (
              <>
                <FormField label="Interest Rate">
                  <div className="relative">
                    <Input
                      type="number"
                      step="0.1"
                      className="pr-7"
                      {...register("interestRate")}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                </FormField>
                <FormField label="Mortgage Term" hint="In years">
                  <Input type="number" {...register("mortgageTerm")} />
                </FormField>
              </>
            )}
            {/* Capital Growth — visible for all non-R2SA types */}
            <FormField
              label="Capital Growth (annual)"
              hint="Used in 5-year projection (default 4%)"
            >
              <div className="relative">
                <Input
                  type="number"
                  step="0.5"
                  className="pr-7"
                  placeholder="4"
                  {...register("capitalGrowthRate")}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
              </div>
            </FormField>

            {/* Bridging Loan Detail Fields */}
            {isBridging && (
              <>
                <FormField label="Monthly Rate" hint="% per month (e.g. 0.75)">
                  <div className="relative">
                    <Input
                      type="number"
                      step="0.05"
                      className="pr-7"
                      {...register("bridgingMonthlyRate")}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                </FormField>
                <FormField label="Loan Term" hint="Months (e.g. 12)">
                  <Input type="number" {...register("bridgingTermMonths")} />
                </FormField>
                <FormField label="Arrangement Fee" hint="% of loan">
                  <div className="relative">
                    <Input
                      type="number"
                      step="0.1"
                      className="pr-7"
                      {...register("bridgingArrangementFee")}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                </FormField>
                <FormField label="Exit Fee" hint="% of loan">
                  <div className="relative">
                    <Input
                      type="number"
                      step="0.1"
                      className="pr-7"
                      {...register("bridgingExitFee")}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                </FormField>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── HMO Room Details ──────────────────────────────────────────── */}
      {isHMO && (
        <div className="flex flex-col gap-4">
          <h3 className="text-base font-semibold text-foreground">HMO Room Details</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Number of Rooms">
              <Input type="number" placeholder="5" {...register("roomCount")} />
            </FormField>
            <FormField label="Avg Room Rate" hint="Monthly rent per room">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input
                  type="number"
                  className="pl-7"
                  placeholder="450"
                  {...register("avgRoomRate")}
                />
              </div>
            </FormField>
          </div>
        </div>
      )}

      {/* ── Rental Income (hidden for HMO — room×rate; hidden for Flip — sell strategy) */}
      {!isHMO && !isFLIP && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">
              {isR2SA ? "Rental Details" : "Rental Income"}
            </h3>
            {prefilled && !isR2SA && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600">
                <Info className="size-3" />
                Required
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              label={isR2SA ? "Monthly Rent to Landlord" : "Expected Monthly Rent"}
              error={errors.monthlyRent?.message}
            >
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input
                  type="number"
                  className="pl-7"
                  placeholder="1200"
                  {...register("monthlyRent")}
                />
              </div>
            </FormField>
            {!isR2SA && (
              <>
                <FormField label="Annual Rent Increase" hint="Estimated %">
                  <div className="relative">
                    <Input
                      type="number"
                      step="0.5"
                      className="pr-7"
                      {...register("annualRentIncrease")}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
                  </div>
                </FormField>
                <FormField label="Void Period" hint="Weeks per year without tenants">
                  <Input type="number" {...register("voidWeeks")} />
                </FormField>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── R2SA — Serviced Accommodation Details ───────────────────── */}
      {isR2SA && (
        <div className="flex flex-col gap-4">
          <h3 className="text-base font-semibold text-foreground">
            Serviced Accommodation Details
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Monthly SA Revenue" hint="Expected gross revenue from bookings">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input
                  type="number"
                  className="pl-7"
                  placeholder="2000"
                  {...register("saMonthlySARevenue")}
                />
              </div>
            </FormField>
            <FormField label="Setup / Furnishing Costs" hint="One-off cost to furnish the property">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input
                  type="number"
                  className="pl-7"
                  placeholder="5000"
                  {...register("saSetupCosts")}
                />
              </div>
            </FormField>
          </div>
        </div>
      )}

      {/* ── Running Costs (hidden for R2SA — ops costs estimated at 30% of SA revenue) */}
      {!isR2SA && (
        <div className="flex flex-col gap-4">
          <h3 className="text-base font-semibold text-foreground">Running Costs</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Management Fee" hint="% of rent">
              <div className="relative">
                <Input
                  type="number"
                  step="0.5"
                  className="pr-7"
                  {...register("managementFeePercent")}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">%</span>
              </div>
            </FormField>
            <FormField label="Insurance (Annual)">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input type="number" className="pl-7" {...register("insurance")} />
              </div>
            </FormField>
            <FormField label="Maintenance (Annual)">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input type="number" className="pl-7" {...register("maintenance")} />
              </div>
            </FormField>
            <FormField label="Ground Rent (Annual)">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input type="number" className="pl-7" {...register("groundRent")} />
              </div>
            </FormField>
            <FormField label="Bills (Monthly)">
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{"£"}</span>
                <Input type="number" className="pl-7" {...register("bills")} />
              </div>
            </FormField>
          </div>
        </div>
      )}

      <Button type="submit" size="xl" className="w-full" disabled={isLoading}>
        {isLoading ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            Analysing Deal...
          </>
        ) : (
          "Analyse This Deal"
        )}
      </Button>
    </form>
  )
}
