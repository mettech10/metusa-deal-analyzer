export type PropertyType = "house" | "flat" | "commercial"
export type PropertyTypeDetail =
  | "terraced"
  | "semi-detached"
  | "detached"
  | "end-of-terrace"
  | "flat-apartment"
  | "bungalow"
  | "maisonette"
  | "other"
export type TenureType = "freehold" | "leasehold"
export type InvestmentType = "btl" | "brr" | "hmo" | "flip" | "r2sa" | "development"
export type PropertyCondition = "excellent" | "good" | "fair" | "needs-work"
export type PurchaseType = "mortgage" | "bridging-loan" | "cash"

export interface PropertyFormData {
  // Property Details
  address: string
  postcode: string
  purchasePrice: number
  propertyType: PropertyType
  propertyTypeDetail?: PropertyTypeDetail  // granular type (terraced, semi, etc.)
  tenureType?: TenureType                  // freehold or leasehold
  leaseYears?: number                      // years remaining on lease (leasehold only)
  investmentType: InvestmentType
  sqft?: number
  bedrooms: number
  condition: PropertyCondition

  // Purchase Costs
  buyerType: "first-time" | "additional"
  refurbishmentBudget: number
  legalFees: number
  surveyCosts: number

  // Financing
  purchaseType: PurchaseType
  depositPercentage: number
  interestRate: number
  mortgageTerm: number
  mortgageType: "repayment" | "interest-only"
  
  // Bridging Loan (if applicable)
  bridgingMonthlyRate?: number // e.g., 0.75 for 0.75% per month
  bridgingTermMonths?: number // typically 3-18 months
  bridgingArrangementFee?: number // % of loan
  bridgingExitFee?: number // % of loan

  // BRR / Flip
  arv?: number // After Repair Value

  // HMO
  roomCount?: number    // number of lettable rooms
  avgRoomRate?: number  // average monthly rent per room

  // Rent-to-SA (R2SA)
  saMonthlySARevenue?: number // expected gross monthly SA revenue
  saSetupCosts?: number       // one-off setup / furnishing costs

  // Projections — user-supplied assumptions
  capitalGrowthRate?: number  // annual property appreciation %, default 4

  // Rental Income
  monthlyRent: number
  annualRentIncrease: number
  voidWeeks: number

  // Running Costs
  managementFeePercent: number
  insurance: number
  maintenance: number
  groundRent: number
  bills: number
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

  // Mortgage / Bridging Loan
  monthlyMortgagePayment: number
  annualMortgageCost: number
  
  // Bridging Loan Specific (if applicable)
  bridgingLoanDetails?: {
    loanAmount: number
    monthlyInterestRate: number
    termMonths: number
    monthlyInterest: number
    totalInterest: number
    arrangementFee: number
    exitFee: number
    totalCost: number
    totalRepayment: number
    apr: number
  }

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
  // New sections for market data
  soldComparables?: SoldComparable[]
  rentComparables?: RentComparable[]
  houseValuation?: HouseValuation
}

export interface SoldComparable {
  address: string
  price: number
  bedrooms: number
  date: string
  type: string
  note?: string
}

export interface RentComparable {
  address: string
  monthlyRent: number
  bedrooms: number
  type: string
  source?: string
}

export interface HouseValuation {
  estimate: number
  confidence: string
  range?: {
    low: number
    high: number
  }
  source?: string
  note?: string
}

// Full structured response from the Flask /ai-analyze endpoint
export interface BackendResults {
  verdict?: "PROCEED" | "REVIEW" | "AVOID"
  deal_score?: number
  deal_score_label?: string
  gross_yield?: number
  net_yield?: number
  monthly_cashflow?: number
  cash_on_cash?: number
  stamp_duty?: number
  deposit_amount?: number
  loan_amount?: number
  monthly_mortgage?: number
  interest_rate?: number
  purchase_price?: number
  address?: string
  postcode?: string
  location?: {
    country?: string
    region?: string
    council?: string
  }
  article_4?: {
    is_article_4: boolean
    known?: boolean
    note?: string
    advice?: string
    hmo_guidance?: string
    social_housing_suggestion?: string
    council?: string
  }
  strategy_recommendations?: {
    BTL?: { suitable: boolean; note: string }
    HMO?: { suitable: boolean; note: string }
    BRR?: { suitable: boolean; note: string }
    FLIP?: { suitable: boolean; note: string }
    SOCIAL_HOUSING?: { suitable: boolean; note: string }
    R2SA?: { suitable: boolean; note: string }
  }
  refurb_estimates?: {
    light?: { total: number; per_sqft_mid?: number; per_sqm?: number }
    medium?: { total: number; per_sqft_mid?: number; per_sqm?: number }
    heavy?: { total: number; per_sqft_mid?: number; per_sqm?: number }
    structural?: { total: number; per_sqft_mid?: number; per_sqm?: number }
  }
  ai_strengths?: string[]
  ai_risks?: string[]
  ai_area?: string
  ai_next_steps?: string[]
  ai_verdict?: string
  sold_comparables?: Array<{
    address: string
    price: number
    bedrooms: number
    date: string
    type: string
    source?: string
  }>
  rent_comparables?: Array<{
    address: string
    monthly_rent: number
    bedrooms?: number
    type?: string
    source?: string
    confidence?: string
  }>
  house_valuation?: {
    estimate: number
    confidence: string
    range?: { low: number; high: number }
    source?: string
    note?: string
  }
  avg_sold_price?: number
  market_source?: string
  risk_flags?: RiskFlag[]
  regional_benchmark?: RegionalBenchmark

  // Airroi SA/R2SA market intelligence
  airroi_market?: {
    avg_nightly_rate?: number
    min_nightly_rate?: number
    max_nightly_rate?: number
    avg_occupancy?: number
    avg_rating?: number
    estimated_monthly_revenue?: number
    listing_count?: number
    revenue_validation?: {
      user_entered: number
      market_estimate: number
      deviation_pct: number
      direction: "above" | "below"
      flag: string
    }
  }
  airroi_nearby_listings?: Array<Record<string, unknown>>
  airroi_market_summary?: Record<string, unknown>
  airroi_occupancy_trend?: Record<string, unknown>
  airroi_adr_trend?: Record<string, unknown>
}

export interface RiskFlag {
  id: string
  name: string
  severity: "HIGH" | "MEDIUM" | "LOW"
  color: "red" | "amber" | "green"
  icon?: string
  description: string
  mitigation: string
}

export interface RegionalBenchmark {
  region_name: string
  postcode_area: string
  data_source: string
  regional_median_yield: number
  your_yield: number
  yield_difference: number
  yield_vs_median_label: string
  yield_percentile: number
  regional_avg_cashflow: number
  your_cashflow: number
  cashflow_difference: number
  cashflow_vs_avg_label: string
  cashflow_percentile: number
  summary: string
}

export interface SensitivityResult {
  // applied slider values
  applied: {
    mortgage_rate: number
    monthly_rent: number
    vacancy_rate: number
  }
  // deal metrics
  deal_score: number
  monthly_cashflow: number
  gross_yield: number
  net_yield: number
  cash_on_cash: number
  verdict: "PROCEED" | "REVIEW" | "AVOID"
  risk_level: string
  risk_flags: RiskFlag[]
  regional_benchmark: RegionalBenchmark
}
