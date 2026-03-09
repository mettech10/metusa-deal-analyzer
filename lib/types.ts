export type PropertyType = "house" | "flat" | "commercial"
export type InvestmentType = "btl" | "brr" | "hmo" | "flip" | "r2sa" | "development"
export type PropertyCondition = "excellent" | "good" | "fair" | "needs-work"
export type PurchaseType = "mortgage" | "bridging-loan" | "cash"

export interface PropertyFormData {
  // Property Details
  address: string
  postcode: string
  purchasePrice: number
  propertyType: PropertyType
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
