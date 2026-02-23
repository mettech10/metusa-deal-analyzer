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
import { Loader2 } from "lucide-react"
import type { PropertyFormData } from "@/lib/types"

const schema = z.object({
  address: z.string().min(1, "Address is required"),
  postcode: z.string().min(1, "Postcode is required"),
  purchasePrice: z.coerce.number().min(1, "Enter a purchase price"),
  propertyType: z.enum(["house", "flat", "hmo", "commercial"]),
  bedrooms: z.coerce.number().min(0).max(20),
  condition: z.enum(["excellent", "good", "fair", "needs-work"]),
  isAdditionalProperty: z.boolean(),
  refurbishmentBudget: z.coerce.number().min(0),
  legalFees: z.coerce.number().min(0),
  surveyCosts: z.coerce.number().min(0),
  purchaseMethod: z.enum(["mortgage", "cash"]),
  depositPercentage: z.coerce.number().min(0).max(100),
  interestRate: z.coerce.number().min(0).max(20),
  mortgageTerm: z.coerce.number().min(1).max(40),
  mortgageType: z.enum(["repayment", "interest-only"]),
  monthlyRent: z.coerce.number().min(0),
  annualRentIncrease: z.coerce.number().min(0).max(20),
  voidWeeks: z.coerce.number().min(0).max(52),
  managementFeePercent: z.coerce.number().min(0).max(100),
  insurance: z.coerce.number().min(0),
  maintenance: z.coerce.number().min(0),
  groundRent: z.coerce.number().min(0),
  serviceCharge: z.coerce.number().min(0),
})

interface PropertyFormProps {
  onSubmit: (data: PropertyFormData) => void
  isLoading: boolean
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

export function PropertyForm({ onSubmit, isLoading }: PropertyFormProps) {
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm<PropertyFormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      address: "",
      postcode: "",
      purchasePrice: 0,
      propertyType: "house",
      bedrooms: 3,
      condition: "good",
      isAdditionalProperty: true,
      refurbishmentBudget: 0,
      legalFees: 1500,
      surveyCosts: 500,
      purchaseMethod: "mortgage",
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
      serviceCharge: 0,
    },
  })

  const purchaseMethod = watch("purchaseMethod")

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-8">
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
                    <SelectItem value="flat">Flat</SelectItem>
                    <SelectItem value="hmo">HMO</SelectItem>
                    <SelectItem value="commercial">Commercial</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
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
          <FormField label="Purchase Method">
            <Controller
              control={control}
              name="purchaseMethod"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="mortgage">Mortgage</SelectItem>
                    <SelectItem value="cash">Cash</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </FormField>
          {purchaseMethod === "mortgage" && (
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
              <FormField label="Mortgage Type">
                <Controller
                  control={control}
                  name="mortgageType"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="repayment">Repayment</SelectItem>
                        <SelectItem value="interest-only">Interest Only</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
              </FormField>
            </>
          )}
        </div>
      </div>

      {/* Rental Income */}
      <div className="flex flex-col gap-4">
        <h3 className="text-base font-semibold text-foreground">
          Rental Income
        </h3>
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
          <FormField label="Service Charge (Annual)">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                {"£"}
              </span>
              <Input
                type="number"
                className="pl-7"
                {...register("serviceCharge")}
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
