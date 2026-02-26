"use client"

import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2, Link2, Info } from "lucide-react"
import type { PropertyFormData } from "@/lib/types"

const schema = z.object({
  address: z.string().min(1, "Address is required"),
  postcode: z.string().min(1, "Postcode is required"),
  purchasePrice: z.coerce.number().min(1, "Enter a purchase price"),
  propertyType: z.enum(["house", "flat", "commercial"]),
  investmentType: z.enum(["btl", "brr", "hmo", "flip", "r2sa", "development"]),
  sqm: z.coerce.number().min(0).optional(),
  bedrooms: z.coerce.number().min(0).max(20),
  condition: z.enum(["excellent", "good", "fair", "needs-work"]),
  isAdditionalProperty: z.boolean(),
  refurbishmentBudget: z.coerce.number().min(0),
  legalFees: z.coerce.number().min(0),
  surveyCosts: z.coerce.number().min(0),
  purchaseType: z.enum(["mortgage", "bridging-loan", "cash"]),
  depositPercentage: z.coerce.number().min(0).max(100),
  interestRate: z.coerce.number().min(0).max(20),
  mortgageTerm: z.coerce.number().min(1).max(40),
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
    sqm: undefined,
    bedrooms: 3,
    condition: "good",
    isAdditionalProperty: true,
    refurbishmentBudget: 0,
    legalFees: 1500,
    surveyCosts: 500,
    purchaseType: "mortgage",
    depositPercentage: 25,
    interestRate: 5.5,
    mortgageTerm: 25,
    mortgageType: "interest-only",
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
    formState: { errors },
  } = useForm<PropertyFormData>({
    resolver: zodResolver(schema),
    defaultValues: { ...baseDefaults, ...defaultValues },
  })

  const purchaseType = watch("purchaseType")

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

      {/* Property Details */}
      <div className="flex flex-col gap-4">
        <h3 className="text-base font-semibold text-foreground">
          Property Details
        </h3>
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
            <Input
              placeholder="e.g. SW1A 2AA"
              {...register("postcode")}
            />
          </FormField>
          <FormField
            label="Purchase Price"
            error={errors.purchasePrice?.message}
          >
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                placeholder="250000"
                {...register("purchasePrice")}
              />
            </div>
          </FormField>
          <FormField label="Property Type">
            <Controller
              control={control}
              name="propertyType"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="house">House</SelectItem>
                    <SelectItem value="flat">Flat/Apartment</SelectItem>
                    <SelectItem value="commercial">Commercial</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </FormField>
          <FormField label="Investment Type">
            <Controller
              control={control}
              name="investmentType"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="btl">BTL</SelectItem>
                    <SelectItem value="brr">BRR</SelectItem>
                    <SelectItem value="hmo">HMO</SelectItem>
                    <SelectItem value="flip">Flip</SelectItem>
                    <SelectItem value="r2sa">R2SA</SelectItem>
                    <SelectItem value="development">Development</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </FormField>
          <FormField label="Sqm" hint="Property size in square meters (optional)">
            <div className="relative">
              <Input
                type="number"
                className="pr-12"
                placeholder="85"
                {...register("sqm")}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                m²
              </span>
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

      {/* Purchase Costs */}
      <div className="flex flex-col gap-4">
        <h3 className="text-base font-semibold text-foreground">
          Purchase Costs
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2 flex items-center gap-3">
            <Controller
              control={control}
              name="isAdditionalProperty"
              render={({ field }) => (
                <Switch
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  id="additional"
                />
              )}
            />
            <Label htmlFor="additional" className="text-sm text-foreground cursor-pointer">
              Additional property (5% SDLT surcharge)
            </Label>
          </div>
          <FormField label="Refurbishment Budget" hint="Leave 0 if none">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("refurbishmentBudget")}
              />
            </div>
          </FormField>
          <FormField label="Legal Fees">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("legalFees")}
              />
            </div>
          </FormField>
          <FormField label="Survey Costs">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("surveyCosts")}
              />
            </div>
          </FormField>
        </div>
      </div>

      {/* Financing */}
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
          {purchaseType !== "cash" && (
            <>
              <FormField label="Deposit" hint="% of purchase price">
                <div className="relative">
                  <Input
                    type="number"
                    step="0.5"
                    className="pr-7"
                    {...register("depositPercentage")}
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    %
                  </span>
                </div>
              </FormField>
              <FormField label="Interest Rate">
                <div className="relative">
                  <Input
                    type="number"
                    step="0.1"
                    className="pr-7"
                    {...register("interestRate")}
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    %
                  </span>
                </div>
              </FormField>
              <FormField label="Mortgage Term" hint="In years">
                <Input type="number" {...register("mortgageTerm")} />
              </FormField>
            </>
          )}
        </div>
      </div>

      {/* Rental Income */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-foreground">
            Rental Income
          </h3>
          {prefilled && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600">
              <Info className="size-3" />
              Required
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="Expected Monthly Rent"
            error={errors.monthlyRent?.message}
          >
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                placeholder="1200"
                {...register("monthlyRent")}
              />
            </div>
          </FormField>
          <FormField label="Annual Rent Increase" hint="Estimated %">
            <div className="relative">
              <Input
                type="number"
                step="0.5"
                className="pr-7"
                {...register("annualRentIncrease")}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                %
              </span>
            </div>
          </FormField>
          <FormField label="Void Period" hint="Weeks per year without tenants">
            <Input type="number" {...register("voidWeeks")} />
          </FormField>
        </div>
      </div>

      {/* Running Costs */}
      <div className="flex flex-col gap-4">
        <h3 className="text-base font-semibold text-foreground">
          Running Costs
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Management Fee" hint="% of rent">
            <div className="relative">
              <Input
                type="number"
                step="0.5"
                className="pr-7"
                {...register("managementFeePercent")}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                %
              </span>
            </div>
          </FormField>
          <FormField label="Insurance (Annual)">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("insurance")}
              />
            </div>
          </FormField>
          <FormField label="Maintenance (Annual)">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("maintenance")}
              />
            </div>
          </FormField>
          <FormField label="Ground Rent (Annual)">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("groundRent")}
              />
            </div>
          </FormField>
          <FormField label="Bills (Monthly)">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("bills")}
              />
            </div>
          </FormField>
        </div>
      </div>

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
