export type PropertyType = "house" | "flat" | "hmo" | "commercial"
export type PropertyCondition = "excellent" | "good" | "fair" | "needs-work"
export type PurchaseMethod = "mortgage" | "cash"
export type MortgageType = "repayment" | "interest-only"

export interface PropertyFormData {
  // Property Details
  address: string
  postcode: string
  purchasePrice: number
  propertyType: PropertyType
  bedrooms: number
  condition: PropertyCondition

  // Purchase Costs
  isAdditionalProperty: boolean
  refurbishmentBudget: number
  legalFees: number
  surveyCosts: number

  // Financing
  purchaseMethod: PurchaseMethod
  depositPercentage: number
  interestRate: number
  mortgageTerm: number
  mortgageType: MortgageType

  // Rental Income
  monthlyRent: number
  annualRentIncrease: number
  voidWeeks: number

  // Running Costs
  managementFeePercent: number
  insurance: number
  maintenance: number
  groundRent: number
  serviceCharge: number
}

export interface CalculationResults {
  // SDLT
  sdltAmount: number
  sdltBreakdown: { band: string; tax: number }[]

  // Total Costs
  totalPurchaseCost: number
  totalCapitalRequired: number
  depositAmount: number
  mortgageAmount: number

  // Mortgage
  monthlyMortgagePayment: number
  annualMortgageCost: number

  // Yields
  grossYield: number
  netYield: number

  // Cash Flow
  monthlyIncome: number
  monthlyExpenses: number
  monthlyCashFlow: number
  annualCashFlow: number

  // ROI
  cashOnCashReturn: number

  // Running Costs Breakdown
  annualRunningCosts: number
  monthlyRunningCosts: number

  // Projections
  fiveYearProjection: YearProjection[]
}

export interface YearProjection {
  year: number
  propertyValue: number
  equity: number
  annualRent: number
  annualCashFlow: number
  cumulativeCashFlow: number
  totalReturn: number
}

export interface AIAnalysis {
  dealScore: number
  summary: string
  strengths: string[]
  risks: string[]
  recommendation: string
}
