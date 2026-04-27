import type { BuyerType, PropertyFormData, CalculationResults, YearProjection } from "./types"

/**
 * Non-residential / mixed-use SDLT bands (England/NI).
 * Applies to pure commercial property, bare land with no dwelling,
 * and mixed-use schemes. No 5% surcharge, no FTB relief.
 *   0% up to 150,000
 *   2% on 150,001 – 250,000
 *   5% above 250,000
 */
function calculateNonResidentialSDLT(price: number): {
  total: number
  breakdown: { band: string; tax: number }[]
} {
  const bands = [
    { threshold: 150000, rate: 0, label: "Up to 150,000 (non-res)" },
    { threshold: 250000, rate: 0.02, label: "150,001 - 250,000 (non-res)" },
    { threshold: Infinity, rate: 0.05, label: "Over 250,000 (non-res)" },
  ]
  let remaining = price
  let total = 0
  const breakdown: { band: string; tax: number }[] = []
  let prevThreshold = 0
  for (const band of bands) {
    const taxable = Math.min(remaining, band.threshold - prevThreshold)
    if (taxable <= 0) break
    const tax = taxable * band.rate
    if (tax > 0) breakdown.push({ band: band.label, tax: Math.round(tax) })
    total += tax
    remaining -= taxable
    prevThreshold = band.threshold
  }
  return { total: Math.round(total), breakdown }
}

/**
 * Calculate UK Stamp Duty Land Tax (SDLT) for England/NI
 * Rates effective from April 2025
 *
 * `rateType` selects between residential bands (default) and
 * non-residential / mixed-use bands (0/2/5%) — used by Development
 * acquisitions of bare land or mixed-use sites.
 *
 * `buyerType`:
 *   - "first-time": FTB relief (0% to £425k, 5% £425k-£625k; lost above £625k)
 *   - "standard":   standard residential bands, no surcharge — primary
 *                   residence buyer who isn't a first-time buyer
 *   - "additional": +5% surcharge on every band — second home / investment
 */
export function calculateSDLT(
  price: number,
  buyerType: BuyerType,
  rateType: "residential" | "non-residential" | "mixed-use" = "residential"
): { total: number; breakdown: { band: string; tax: number }[] } {
  if (rateType === "non-residential" || rateType === "mixed-use") {
    return calculateNonResidentialSDLT(price)
  }
  // First-time buyer relief: 0% up to £425k, 5% on £425k–£625k, standard above £625k
  // (relief removed entirely if price > £625,000)
  if (buyerType === "first-time" && price <= 625000) {
    const bands = [
      { threshold: 425000, rate: 0, label: "Up to 425,000" },
      { threshold: 625000, rate: 0.05, label: "425,001 - 625,000" },
    ]
    let remaining = price
    let total = 0
    const breakdown: { band: string; tax: number }[] = []
    let prevThreshold = 0
    for (const band of bands) {
      const taxable = Math.min(remaining, band.threshold - prevThreshold)
      if (taxable <= 0) break
      const tax = taxable * band.rate
      if (tax > 0) breakdown.push({ band: band.label, tax: Math.round(tax) })
      total += tax
      remaining -= taxable
      prevThreshold = band.threshold
    }
    return { total: Math.round(total), breakdown }
  }

  // Standard residential bands.
  // FTB above £625k loses relief entirely → falls through here as "standard".
  // "additional" applies a 5% surcharge on every band.
  const surcharge = buyerType === "additional" ? 0.05 : 0

  const bands = [
    { threshold: 125000, rate: 0, label: "Up to 125,000" },
    { threshold: 250000, rate: 0.02, label: "125,001 - 250,000" },
    { threshold: 925000, rate: 0.05, label: "250,001 - 925,000" },
    { threshold: 1500000, rate: 0.10, label: "925,001 - 1,500,000" },
    { threshold: Infinity, rate: 0.12, label: "Over 1,500,000" },
  ]

  let remaining = price
  let total = 0
  const breakdown: { band: string; tax: number }[] = []
  let prevThreshold = 0

  for (const band of bands) {
    const taxable = Math.min(remaining, band.threshold - prevThreshold)
    if (taxable <= 0) break

    const effectiveRate = band.rate + surcharge
    const tax = taxable * effectiveRate

    if (tax > 0) {
      breakdown.push({
        band: band.label,
        tax: Math.round(tax),
      })
    }

    total += tax
    remaining -= taxable
    prevThreshold = band.threshold
  }

  // If additional property and price > 0, there's always at least the surcharge on the first band
  if (buyerType === "additional" && price > 0 && price <= 125000) {
    const tax = price * surcharge
    total = tax
    breakdown.length = 0
    breakdown.push({ band: "Up to 125,000", tax: Math.round(tax) })
  }

  return { total: Math.round(total), breakdown }
}

/**
 * Calculate monthly mortgage payment
 */
export function calculateMortgagePayment(
  principal: number,
  annualRate: number,
  termYears: number,
  type: "repayment" | "interest-only"
): number {
  if (principal <= 0 || annualRate <= 0) return 0

  const monthlyRate = annualRate / 100 / 12

  if (type === "interest-only") {
    return Math.round(principal * monthlyRate * 100) / 100
  }

  // Repayment mortgage (annuity formula)
  const n = termYears * 12
  const payment =
    (principal * (monthlyRate * Math.pow(1 + monthlyRate, n))) /
    (Math.pow(1 + monthlyRate, n) - 1)

  return Math.round(payment * 100) / 100
}

/**
 * Calculate bridging loan costs
 * Bridging loans typically:
 * - Higher interest (0.5-1.5% per month = 6-18% annual)
 * - Shorter term (3-18 months)
 * - Arrangement fee (1-2% of loan)
 * - Exit fee (0-1% of loan)
 * - Interest rolled up (paid at end) or retained (deducted upfront)
 */
export function calculateBridgingLoan(
  loanAmount: number,
  monthlyRate: number, // e.g., 0.75 for 0.75% per month
  termMonths: number,
  arrangementFeePercent: number = 1,
  exitFeePercent: number = 0.5,
  interestRolledUp: boolean = true
): {
  monthlyInterest: number
  totalInterest: number
  arrangementFee: number
  exitFee: number
  totalCost: number
  totalRepayment: number
  apr: number
} {
  if (loanAmount <= 0 || monthlyRate <= 0) {
    return {
      monthlyInterest: 0,
      totalInterest: 0,
      arrangementFee: 0,
      exitFee: 0,
      totalCost: 0,
      totalRepayment: 0,
      apr: 0
    }
  }

  // Monthly interest charge
  const monthlyInterest = Math.round(loanAmount * (monthlyRate / 100) * 100) / 100
  
  // Total interest over term
  const totalInterest = Math.round(monthlyInterest * termMonths * 100) / 100
  
  // Fees
  const arrangementFee = Math.round(loanAmount * (arrangementFeePercent / 100))
  const exitFee = Math.round(loanAmount * (exitFeePercent / 100))
  
  // Total cost of bridging
  const totalCost = totalInterest + arrangementFee + exitFee
  
  // Total to repay
  const totalRepayment = loanAmount + (interestRolledUp ? totalInterest : 0) + exitFee
  
  // True APR: compound monthly rate → effective annual + fee drag (matches Flask backend)
  const effectiveAnnual = (Math.pow(1 + monthlyRate / 100, 12) - 1) * 100
  const feeDrag = (arrangementFeePercent + exitFeePercent) / Math.max(termMonths / 12, 0.083)
  const apr = Math.round((effectiveAnnual + feeDrag) * 100) / 100
  
  return {
    monthlyInterest,
    totalInterest,
    arrangementFee,
    exitFee,
    totalCost,
    totalRepayment,
    apr
  }
}

/**
 * Calculate gross rental yield
 */
export function calculateGrossYield(annualRent: number, purchasePrice: number): number {
  if (purchasePrice <= 0) return 0
  return Math.round((annualRent / purchasePrice) * 10000) / 100
}

/**
 * Calculate net rental yield
 */
export function calculateNetYield(
  annualRent: number,
  annualCosts: number,
  purchasePrice: number
): number {
  if (purchasePrice <= 0) return 0
  return Math.round(((annualRent - annualCosts) / purchasePrice) * 10000) / 100
}

/**
 * Calculate 5-year projection
 */
function calculateProjection(
  purchasePrice: number,
  annualRent: number,
  annualCashFlow: number,
  mortgageAmount: number,
  capitalGrowthRate: number = 3,
  rentGrowthRate: number = 2
): YearProjection[] {
  const projections: YearProjection[] = []
  let cumulativeCashFlow = 0

  for (let year = 1; year <= 5; year++) {
    const growthMultiplier = Math.pow(1 + capitalGrowthRate / 100, year)
    const rentMultiplier = Math.pow(1 + rentGrowthRate / 100, year)

    const propertyValue = Math.round(purchasePrice * growthMultiplier)
    const equity = propertyValue - mortgageAmount
    const projectedRent = Math.round(annualRent * rentMultiplier)
    const projectedCashFlow = Math.round(annualCashFlow * rentMultiplier)
    cumulativeCashFlow += projectedCashFlow

    projections.push({
      year,
      propertyValue,
      equity,
      annualRent: projectedRent,
      annualCashFlow: projectedCashFlow,
      cumulativeCashFlow,
      totalReturn: equity - (purchasePrice - mortgageAmount) + cumulativeCashFlow,
    })
  }

  return projections
}

/**
 * Run full analysis calculations
 */
export function calculateAll(data: PropertyFormData): CalculationResults {
  // ── Property Development (new-build / conversion / refurb) ──────────────
  // Delegates the full cost-stack + finance + RLV + IRR calc to the
  // dedicated engine and stuffs the result onto CalculationResults.development.
  // We still populate the base CalculationResults fields the shared UI reads
  // (SDLT, TDC, equity, yields=0, no monthly cashflow) so downstream code
  // never has to null-check.
  if (data.investmentType === "development") {
    // Lazy import to avoid a circular (developmentCalculations imports
    // calculateSDLT from this file).
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { calculateDevelopment } =
      require("./developmentCalculations") as typeof import("./developmentCalculations")
    const dev = calculateDevelopment(data)
    const { total: sdltAmount, breakdown: sdltBreakdown } = calculateSDLT(
      data.purchasePrice,
      data.buyerType,
      data.sdltRateType ?? "residential",
    )
    return {
      sdltAmount,
      sdltBreakdown,
      totalPurchaseCost: dev.totalDevelopmentCost,
      totalCapitalRequired: dev.equityRequired,
      depositAmount: dev.equityRequired,
      mortgageAmount: dev.financeFacilityLoan,
      monthlyMortgagePayment: 0,
      annualMortgageCost: 0,
      bridgingLoanDetails: undefined,
      grossYield: 0,
      netYield: 0,
      monthlyIncome: 0,
      monthlyExpenses: 0,
      monthlyCashFlow: 0,
      annualCashFlow: 0,
      cashOnCashReturn: dev.roe,
      annualRunningCosts: 0,
      monthlyRunningCosts: 0,
      development: dev,
      fiveYearProjection: [],
    }
  }

  // ── R2SA: rent the property from a landlord, sublet as serviced accommodation ──
  if (data.investmentType === "r2sa") {
    const saRevenue   = data.saMonthlySARevenue || 0
    const rentPaid    = data.monthlyRent         // rent paid to the landlord
    const setupCosts  = data.saSetupCosts || 5000
    // Operating costs: cleaning, utilities, platform fees (~30% of SA revenue)
    const monthlyOpCosts  = saRevenue * 0.30
    const monthlyExpenses = Math.round((rentPaid + monthlyOpCosts) * 100) / 100
    const monthlyCashFlow = Math.round((saRevenue - monthlyExpenses) * 100) / 100
    const annualCashFlow  = Math.round(monthlyCashFlow * 12 * 100) / 100
    const cashOnCashReturn =
      setupCosts > 0 ? Math.round((annualCashFlow / setupCosts) * 10000) / 100 : 0

    return {
      sdltAmount: 0,
      sdltBreakdown: [],
      totalPurchaseCost: 0,
      totalCapitalRequired: setupCosts,
      depositAmount: 0,
      mortgageAmount: 0,
      monthlyMortgagePayment: 0,
      annualMortgageCost: 0,
      bridgingLoanDetails: undefined,
      grossYield: 0,
      netYield: 0,
      monthlyIncome: Math.round(saRevenue * 100) / 100,
      monthlyExpenses,
      monthlyCashFlow,
      annualCashFlow,
      cashOnCashReturn,
      annualRunningCosts: Math.round(monthlyExpenses * 12 * 100) / 100,
      monthlyRunningCosts: monthlyExpenses,
      fiveYearProjection: [],
    }
  }

  const { total: sdltAmount, breakdown: sdltBreakdown } = calculateSDLT(
    data.purchasePrice,
    data.buyerType,
    data.sdltRateType
  )

  // Deposit & Mortgage
  const depositAmount =
    data.purchaseType === "cash"
      ? data.purchasePrice
      : Math.round(data.purchasePrice * (data.depositPercentage / 100))

  const mortgageAmount =
    data.purchaseType === "cash" ? 0 : data.purchasePrice - depositAmount

  // Total purchase cost
  const totalPurchaseCost =
    data.purchasePrice +
    sdltAmount +
    data.legalFees +
    data.surveyCosts +
    data.refurbishmentBudget

  // Total capital required (deposit + all costs except the mortgage portion)
  const totalCapitalRequired =
    depositAmount +
    sdltAmount +
    data.legalFees +
    data.surveyCosts +
    data.refurbishmentBudget

  // Mortgage or Bridging Loan calculations
  let monthlyMortgagePayment = 0
  let annualMortgageCost = 0
  let bridgingLoanDetails = undefined

  if (data.purchaseType === "cash") {
    // Cash purchase - no financing costs
    monthlyMortgagePayment = 0
    annualMortgageCost = 0
  } else if (data.purchaseType === "bridging-loan") {
    // Bridging loan calculations
    // Default bridging: 0.75% per month, 12 months, 1% arrangement, 0.5% exit
    const bridgingMonthlyRate = data.bridgingMonthlyRate || 0.75 // 0.75% per month default
    const bridgingTermMonths = data.bridgingTermMonths || 12 // 12 months default
    
    const bridgingResult = calculateBridgingLoan(
      mortgageAmount,
      bridgingMonthlyRate,
      bridgingTermMonths,
      data.bridgingArrangementFee || 1, // 1% default
      data.bridgingExitFee || 0.5, // 0.5% default
      true // interest rolled up
    )
    
    // Map to the correct type format
    bridgingLoanDetails = {
      loanAmount: mortgageAmount,
      monthlyInterestRate: bridgingMonthlyRate,
      termMonths: bridgingTermMonths,
      monthlyInterest: bridgingResult.monthlyInterest,
      totalInterest: bridgingResult.totalInterest,
      arrangementFee: bridgingResult.arrangementFee,
      exitFee: bridgingResult.exitFee,
      totalCost: bridgingResult.totalCost,
      totalRepayment: bridgingResult.totalRepayment,
      apr: bridgingResult.apr
    }
    
    // For cash flow calculations, bridging has no monthly payments
    // (interest is rolled up and paid at exit)
    monthlyMortgagePayment = 0
    annualMortgageCost = 0
  } else {
    // Standard mortgage
    monthlyMortgagePayment = calculateMortgagePayment(
      mortgageAmount,
      data.interestRate,
      data.mortgageTerm,
      data.mortgageType
    )
    annualMortgageCost = monthlyMortgagePayment * 12
  }

  // Rental income.
  // contractAnnualRent = the rent on the lease (what you'd quote in marketing).
  // annualRent          = that figure void-adjusted (effective income for cashflow).
  // Gross yield uses contractAnnualRent (industry-standard); cashflow uses annualRent.
  const effectiveWeeks = 52 - data.voidWeeks
  const contractAnnualRent = data.monthlyRent * 12
  const annualRent = Math.round(contractAnnualRent * (effectiveWeeks / 52))
  const monthlyIncome = Math.round((annualRent / 12) * 100) / 100

  // Running costs.
  // The form labels: "Insurance (Annual)", "Maintenance (Annual)", "Ground Rent
  // (Annual)" — those three are entered annually and divided by 12 for the
  // monthly view. "Bills (Monthly)" is entered monthly and used as-is. This
  // distinction matters: previously bills were also divided by 12, which
  // 12× understated the bills line.
  const monthlyManagement = data.monthlyRent * (data.managementFeePercent / 100)
  const monthlyInsurance = data.insurance / 12
  const monthlyMaintenance = data.maintenance / 12
  const monthlyGroundRent = data.groundRent / 12
  const monthlyBills = data.bills

  const monthlyRunningCosts =
    Math.round(
      (monthlyManagement +
        monthlyInsurance +
        monthlyMaintenance +
        monthlyGroundRent +
        monthlyBills) *
        100
    ) / 100

  const annualRunningCosts = Math.round(monthlyRunningCosts * 12 * 100) / 100

  // Total monthly expenses
  const monthlyExpenses =
    Math.round((monthlyMortgagePayment + monthlyRunningCosts) * 100) / 100

  // Cash flow
  const monthlyCashFlow = Math.round((monthlyIncome - monthlyExpenses) * 100) / 100
  const annualCashFlow = Math.round(monthlyCashFlow * 12 * 100) / 100

  // Yields.
  // Gross uses contract rent (the lease figure), per UK convention.
  // Net uses void-adjusted rent so it reflects actual deliverable income.
  const grossYield = calculateGrossYield(contractAnnualRent, data.purchasePrice)
  const netYield = calculateNetYield(
    annualRent,
    annualRunningCosts + annualMortgageCost,
    data.purchasePrice
  )

  // ROI (cash-on-cash return)
  const cashOnCashReturn =
    totalCapitalRequired > 0
      ? Math.round((annualCashFlow / totalCapitalRequired) * 10000) / 100
      : 0

  // 5-year projection — use user-supplied capitalGrowthRate (default 4%, clamped 0–30%)
  const capitalGrowthRate = Math.min(Math.max(data.capitalGrowthRate ?? 4, 0), 30)
  const fiveYearProjection = calculateProjection(
    data.purchasePrice,
    annualRent,
    annualCashFlow,
    mortgageAmount,
    capitalGrowthRate,
    data.annualRentIncrease
  )

  return {
    sdltAmount,
    sdltBreakdown,
    totalPurchaseCost,
    totalCapitalRequired,
    depositAmount,
    mortgageAmount,
    monthlyMortgagePayment,
    annualMortgageCost,
    bridgingLoanDetails,
    grossYield,
    netYield,
    monthlyIncome,
    monthlyExpenses,
    monthlyCashFlow,
    annualCashFlow,
    cashOnCashReturn,
    annualRunningCosts,
    monthlyRunningCosts,
    fiveYearProjection,
  }
}

/**
 * Format number as GBP currency
 */
export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

/**
 * Format as percentage
 */
export function formatPercent(value: number): string {
  return `${value.toFixed(2)}%`
}

/**
 * Calculate deal score from cash-on-cash ROI (%).
 *
 * Bands (linear interpolation within each):
 *   ROI ≥ 20%        → 100
 *   15% ≤ ROI < 20%  → 75 – 100
 *   10% ≤ ROI < 15%  → 50 – 75
 *   5%  ≤ ROI < 10%  → 25 – 50
 *   0%  ≤ ROI < 5%   → 0  – 25
 *   ROI < 0%         → 0
 */
export function calculateDealScore(cashOnCashReturn: number): number {
  if (cashOnCashReturn >= 20) return 100
  if (cashOnCashReturn >= 15) return Math.round(75 + ((cashOnCashReturn - 15) / 5) * 25)
  if (cashOnCashReturn >= 10) return Math.round(50 + ((cashOnCashReturn - 10) / 5) * 25)
  if (cashOnCashReturn >= 5)  return Math.round(25 + ((cashOnCashReturn - 5)  / 5) * 25)
  if (cashOnCashReturn >= 0)  return Math.round((cashOnCashReturn / 5) * 25)
  return 0
}

/**
 * Estimate refurbishment cost based on floor area and condition.
 * Rates are per sq metre, adjusted for London postcodes and property type.
 *
 * Condition → mid-tier cost/sqft (2024-25 UK benchmarks, Checkatrade / BRRR):
 *   excellent  →  £0     (move-in ready, no refurb)
 *   good       →  £18    (light: redecoration, some flooring/fixtures)
 *   fair       →  £35    (medium: new kitchen + bathroom, full redecoration)
 *   needs-work →  £60    (full: kitchen, bathroom, rewire, replumb, damp, windows)
 */
export function estimateRefurbCost(
  sqft: number,
  condition: string,
  propertyType: string,
  postcode?: string
): number {
  if (!sqft || sqft <= 0) return 0

  // Mid-tier cost per sqft aligned with backend get_refurb_estimate tiers
  const costPerSqft: Record<string, number> = {
    excellent: 0,
    good: 18,
    fair: 35,
    "needs-work": 60,
  }

  const base = costPerSqft[condition] ?? 35

  // Property type multipliers (detached/bungalow cost more; flats less)
  const typeMultipliers: Record<string, number> = {
    flat: 0.85,
    house: 0.95,
    commercial: 1.0,
  }
  const typeMultiplier = typeMultipliers[propertyType] ?? 0.95

  // Regional multipliers from postcode prefix — matches backend REGION_MULT table
  const pc = (postcode ?? "").toUpperCase().replace(/\s/g, "")
  const REGION_MULT: Record<string, number> = {
    EC: 1.50, WC: 1.50, W1: 1.50, SW1: 1.50, SE1: 1.45, N1: 1.40,
    SW: 1.35, W: 1.35, NW: 1.30, E: 1.30,
    N: 1.25, SE: 1.25, KT: 1.25, TW: 1.25,
    BR: 1.20, CR: 1.20, RM: 1.20, HA: 1.20, UB: 1.20,
    SM: 1.20, WD: 1.15, EN: 1.15, IG: 1.15, DA: 1.15,
    GU: 1.20, RH: 1.20, SL: 1.15, AL: 1.15, OX: 1.15,
    RG: 1.15, HP: 1.10, CM: 1.10, BN: 1.10, TN: 1.10, ME: 1.05, CT: 1.05,
    B: 0.95, CV: 0.92, LE: 0.92, NG: 0.90, DE: 0.90, ST: 0.90,
    M: 0.90, L: 0.88, LS: 0.88, S: 0.87, NE: 0.87, HU: 0.85,
    PR: 0.87, BB: 0.85, BL: 0.85, OL: 0.85,
    EH: 0.90, G: 0.88, AB: 0.85, CF: 0.85, SA: 0.82,
  }
  // Match longest prefix first to avoid 'N' shadowing 'NW'
  const areaMultiplier = Object.keys(REGION_MULT)
    .sort((a, b) => b.length - a.length)
    .reduce((mult, prefix) => pc.startsWith(prefix) ? REGION_MULT[prefix] : mult, 1.0)

  return Math.round(sqft * base * typeMultiplier * areaMultiplier)
}
