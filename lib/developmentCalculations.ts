/**
 * Property Development calculation engine.
 *
 * Full cost-stack → finance → exit → profit → viability pipeline for
 * new-build / conversion / refurbishment schemes. Called from the
 * `investmentType === "development"` branch in calculateAll. The UI
 * renders results via CalculationResults.development (see types.ts).
 *
 * Conventions:
 *  - All £ values are rounded to the nearest pound in the result.
 *  - All percentages in the result are 0–100 (not 0–1).
 *  - The engine is total — every field is populated, even on missing
 *    input (fields default to 0 / empty array), so the UI never needs
 *    to conditionally render. "Enter manually" contract preserved.
 *  - Finance interest uses the industry-standard 50% average-utilisation
 *    approximation on the construction drawdown — exact only with a
 *    full month-by-month drawdown schedule, which is out of scope.
 *  - Residual land value back-solves a 20% profit-on-cost target (the
 *    RICS "blue-book" benchmark for viability appraisals).
 */

import type { PropertyFormData } from "./types"
import { calculateSDLT } from "./calculations"

/** Per-unit-type GDV contribution. */
export interface DevelopmentUnitLine {
  unitType: string
  numberOfUnits: number
  avgSizeM2: number
  salePricePerUnit: number
  gdv: number
}

/** Line item in the full development cost stack. */
export interface DevelopmentCostLine {
  label: string
  amount: number
  /** Percentage of Total Development Cost (for stack visualisation). */
  percentOfTDC: number
}

/** Viability flag surfaced to the UI. */
export interface DevelopmentFlag {
  severity: "info" | "warn" | "danger"
  message: string
}

export interface DevelopmentResult {
  // ── Unit mix summary ────────────────────────────────────
  totalUnits: number
  totalGIA: number                   // sum of numberOfUnits × avgSizeM2
  totalGDV: number                   // sum of numberOfUnits × salePricePerUnit
  avgGDVPerUnit: number
  avgGDVPerM2: number
  unitLines: DevelopmentUnitLine[]

  // ── Acquisition ─────────────────────────────────────────
  acquisitionPrice: number
  acquisitionSDLT: number
  acquisitionLegal: number
  acquisitionSurvey: number
  acquisitionTotal: number
  sdltRateTypeUsed: "residential" | "non-residential" | "mixed-use"

  // ── Construction ────────────────────────────────────────
  constructionBase: number           // GIA × £/m²
  constructionAbnormals: number
  constructionContingency: number
  constructionTotal: number
  buildCostPerM2Used: number

  // ── Professional fees ───────────────────────────────────
  feeArchitect: number
  feeStructural: number
  feeQS: number
  feePM: number
  feePlanningConsultant: number
  feeBuildingControl: number
  feeWarranty: number
  professionalFeesTotal: number

  // ── Planning obligations ────────────────────────────────
  cilTotal: number
  s106Total: number
  affordableHousingDiscount: number   // £ revenue reduction from affordable %
  buildingRegsFee: number
  planningObligationsTotal: number

  // ── Exit / sales costs ──────────────────────────────────
  salesAgentFee: number
  salesLegalTotal: number
  marketingTotal: number
  exitCostsTotal: number

  // ── Development finance ─────────────────────────────────
  financeFacilityLoan: number        // total loan facility: LTC × costs ex-finance
  financeDay1Drawdown: number        // advanced at completion against land
  financeArrangementFee: number
  financeExitFee: number
  financeMonitoringTotal: number     // monthly × term
  financeInterest: number            // total interest over term (rolled or serviced)
  financeCostTotal: number           // arrangement + exit + monitoring + interest
  financeTermMonths: number
  financeRateUsed: number
  financeRolledUp: boolean

  // ── Cost totals ─────────────────────────────────────────
  totalCostExFinance: number         // acq + construction + fees + planning + exit
  totalDevelopmentCost: number       // + finance
  costStack: DevelopmentCostLine[]   // ordered, for stacked-bar UI

  // ── Profit & ratios ─────────────────────────────────────
  grossProfit: number                // GDV - TDC (after sales)
  profitOnGDV: number                // %
  profitOnCost: number               // %

  // ── Equity & leverage ───────────────────────────────────
  equityRequired: number             // TDC ex-finance not covered by loan
  peakFunding: number                // loan at practical completion (rolled-up case)
  ltgdv: number                      // %
  ltc: number                        // %

  // ── Returns ─────────────────────────────────────────────
  roe: number                        // profit / equity (%)
  annualisedROI: number              // ROE × 12 / term (%)
  irr: number                        // annualised IRR from two-point cashflow (%)

  // ── Residual land value (back-solved) ───────────────────
  residualLandValue: number          // max land price at 20% profit-on-cost target
  landPremiumOverAsk: number         // RLV - acquisitionPrice (negative = overpaying)
  rlvProfitTargetPercent: number     // 20 — exposed for label clarity

  // ── Viability ───────────────────────────────────────────
  flags: DevelopmentFlag[]
  affordableHousingTriggered: boolean
  dealScore: number                  // 0–100
  dealScoreLabel: string             // "Excellent" | "Good" | "Fair" | "Weak" | "Poor"
}

/** Round to nearest pound. */
const r = (n: number) => Math.round(n)
/** Round to 2 decimal places (for ratios/percents). */
const r2 = (n: number) => Math.round(n * 100) / 100

/**
 * Main entry. Never throws — missing fields fall back to 0.
 * Returns a fully-populated DevelopmentResult.
 */
export function calculateDevelopment(
  data: PropertyFormData,
): DevelopmentResult {
  // ── 1 · Unit mix ────────────────────────────────────────
  const units = data.devUnitMix ?? []
  const unitLines: DevelopmentUnitLine[] = units.map((u) => ({
    unitType: u.unitType,
    numberOfUnits: Number(u.numberOfUnits) || 0,
    avgSizeM2: Number(u.avgSizeM2) || 0,
    salePricePerUnit: Number(u.salePricePerUnit) || 0,
    gdv:
      (Number(u.numberOfUnits) || 0) * (Number(u.salePricePerUnit) || 0),
  }))
  const totalUnits = unitLines.reduce((s, u) => s + u.numberOfUnits, 0)
  const totalGIA = unitLines.reduce(
    (s, u) => s + u.numberOfUnits * u.avgSizeM2,
    0,
  )
  const totalGDV = unitLines.reduce((s, u) => s + u.gdv, 0)
  const avgGDVPerUnit = totalUnits > 0 ? totalGDV / totalUnits : 0
  const avgGDVPerM2 = totalGIA > 0 ? totalGDV / totalGIA : 0

  // ── 2 · Acquisition ─────────────────────────────────────
  const acquisitionPrice = Number(data.purchasePrice) || 0
  const sdltRateTypeUsed = data.sdltRateType ?? "residential"
  const { total: acquisitionSDLT } = calculateSDLT(
    acquisitionPrice,
    data.buyerType,
    sdltRateTypeUsed,
  )
  const acquisitionLegal = Number(data.legalFees) || 0
  const acquisitionSurvey = Number(data.surveyCosts) || 0
  const acquisitionTotal =
    acquisitionPrice + acquisitionSDLT + acquisitionLegal + acquisitionSurvey

  // ── 3 · Construction ────────────────────────────────────
  const buildCostPerM2Used = Number(data.devBuildCostPerM2) || 0
  const constructionBase = totalGIA * buildCostPerM2Used
  const constructionAbnormals = Number(data.devAbnormals) || 0
  const contingencyPct = Number(data.devContingencyPercent) || 0
  const constructionContingency =
    (constructionBase + constructionAbnormals) * (contingencyPct / 100)
  const constructionTotal =
    constructionBase + constructionAbnormals + constructionContingency

  // ── 4 · Professional fees (% of construction) ──────────
  const feeArchitect =
    constructionTotal * ((Number(data.devArchitectPercent) || 0) / 100)
  const feeStructural =
    constructionTotal *
    ((Number(data.devStructuralEngineerPercent) || 0) / 100)
  const feeQS = constructionTotal * ((Number(data.devQsPercent) || 0) / 100)
  const feePM =
    constructionTotal * ((Number(data.devProjectManagerPercent) || 0) / 100)
  const feePlanningConsultant = Number(data.devPlanningConsultantFixed) || 0
  const feeBuildingControl = Number(data.devBuildingControlFixed) || 0
  // Warranty (NHBC etc.) typically % of GDV
  const feeWarranty =
    totalGDV * ((Number(data.devWarrantyPercent) || 0) / 100)
  const professionalFeesTotal =
    feeArchitect +
    feeStructural +
    feeQS +
    feePM +
    feePlanningConsultant +
    feeBuildingControl +
    feeWarranty

  // ── 5 · Planning obligations ────────────────────────────
  const cilTotal = totalGIA * (Number(data.devCILRatePerM2) || 0)
  const s106Total = totalUnits * (Number(data.devS106PerUnit) || 0)
  const affordablePct = Number(data.devAffordableHousingPercent) || 0
  // Affordable units typically sell at ~50% discount to RP — model as
  // revenue-side discount. For cost-stack we only surface the £ impact.
  const affordableHousingDiscount =
    totalGDV * (affordablePct / 100) * 0.5
  const buildingRegsFee = Number(data.devBuildingRegsFixed) || 0
  const planningObligationsTotal = cilTotal + s106Total + buildingRegsFee

  // Net revenue after affordable discount — used from here onward
  const netGDV = totalGDV - affordableHousingDiscount

  // ── 6 · Exit / sales costs ──────────────────────────────
  const salesAgentFee =
    netGDV * ((Number(data.devSalesAgentPercent) || 0) / 100)
  const salesLegalTotal =
    totalUnits * (Number(data.devSalesLegalPerUnit) || 0)
  const marketingTotal =
    (Number(data.devMarketingCostsFixed) || 0) +
    totalUnits * (Number(data.devMarketingPerUnit) || 0)
  const exitCostsTotal = salesAgentFee + salesLegalTotal + marketingTotal

  // ── 7 · Finance ─────────────────────────────────────────
  const ltcPct = Number(data.devFinanceLTC) || 0
  const day1Pct = Number(data.devFinanceDay1Percent) || 0
  const financeRateUsed = Number(data.devFinanceRate) || 0
  const financeTermMonths = Number(data.devFinanceTermMonths) || 0
  const arrangementPct = Number(data.devFinanceArrangementFeePercent) || 0
  const exitPct = Number(data.devFinanceExitFeePercent) || 0
  const monitoringFeeMonthly =
    Number(data.devFinanceMonitoringFeeMonthly) || 0
  const financeRolledUp = Boolean(data.devFinanceRolledUp)

  // Loan facility = LTC × (all costs except finance, except exit).
  // Exit is excluded because lenders size against acquisition +
  // construction + soft costs, not post-sale expenses.
  const costsForLoanBase =
    acquisitionTotal +
    constructionTotal +
    professionalFeesTotal +
    planningObligationsTotal
  const financeFacilityLoan = costsForLoanBase * (ltcPct / 100)
  const financeDay1Drawdown = acquisitionPrice * (day1Pct / 100)
  // Construction drawdown is the residual, drawn over the build period.
  const constructionDrawdown = Math.max(
    0,
    financeFacilityLoan - financeDay1Drawdown,
  )

  const financeArrangementFee =
    financeFacilityLoan * (arrangementPct / 100)
  const financeExitFee = financeFacilityLoan * (exitPct / 100)
  const financeMonitoringTotal =
    monitoringFeeMonthly * financeTermMonths

  // Interest: day-1 draws for full term; construction tranche uses
  // 50% avg utilisation (industry convention for dev appraisals).
  const yearsTerm = financeTermMonths / 12
  const rateDecimal = financeRateUsed / 100
  const day1Interest =
    financeDay1Drawdown * rateDecimal * yearsTerm
  const constructionInterest =
    constructionDrawdown * rateDecimal * yearsTerm * 0.5
  const financeInterest = day1Interest + constructionInterest

  const financeCostTotal =
    financeArrangementFee +
    financeExitFee +
    financeMonitoringTotal +
    financeInterest

  // ── 8 · Cost totals ─────────────────────────────────────
  const totalCostExFinance =
    acquisitionTotal +
    constructionTotal +
    professionalFeesTotal +
    planningObligationsTotal +
    exitCostsTotal
  const totalDevelopmentCost = totalCostExFinance + financeCostTotal

  // ── 9 · Profit ──────────────────────────────────────────
  const grossProfit = netGDV - totalDevelopmentCost
  const profitOnGDV =
    netGDV > 0 ? (grossProfit / netGDV) * 100 : 0
  const profitOnCost =
    totalDevelopmentCost > 0
      ? (grossProfit / totalDevelopmentCost) * 100
      : 0

  // ── 10 · Equity & leverage ──────────────────────────────
  // Equity is TDC ex-finance that the loan doesn't cover, plus
  // any serviced interest (paid from equity, not rolled up).
  const servicedInterest = financeRolledUp ? 0 : financeInterest
  const equityRequired = Math.max(
    0,
    totalCostExFinance - financeFacilityLoan + servicedInterest,
  )
  // Peak funding: at practical completion, loan + rolled-up interest.
  const peakFunding =
    financeFacilityLoan + (financeRolledUp ? financeInterest : 0)
  const ltgdv = netGDV > 0 ? (peakFunding / netGDV) * 100 : 0
  const ltc =
    totalCostExFinance > 0
      ? (financeFacilityLoan / totalCostExFinance) * 100
      : 0

  // ── 11 · Returns ────────────────────────────────────────
  const roe = equityRequired > 0 ? (grossProfit / equityRequired) * 100 : 0
  const annualisedROI =
    equityRequired > 0 && financeTermMonths > 0
      ? roe * (12 / financeTermMonths)
      : 0
  // Two-point IRR: equity out at month 0, equity + profit back at term.
  let irr = 0
  if (
    equityRequired > 0 &&
    financeTermMonths > 0 &&
    grossProfit > -equityRequired
  ) {
    const multiple = (equityRequired + grossProfit) / equityRequired
    // Guard against negative bases with fractional exponents
    if (multiple > 0) {
      const monthly = Math.pow(multiple, 1 / financeTermMonths) - 1
      irr = (Math.pow(1 + monthly, 12) - 1) * 100
    }
  }

  // ── 12 · Residual land value (20% profit-on-cost target) ─
  // Target: (netGDV - land_total_acq - other_costs) / (land_total_acq + other_costs) = 0.20
  // Solving for land_total_acq:
  //   land_total_acq = netGDV / 1.20 - other_costs
  // Then back out purchase-price component (SDLT approx at current rate).
  const rlvProfitTargetPercent = 20
  const otherCosts =
    constructionTotal +
    professionalFeesTotal +
    planningObligationsTotal +
    exitCostsTotal +
    financeCostTotal +
    acquisitionLegal +
    acquisitionSurvey
  const rlvAcqTotalTarget =
    netGDV / (1 + rlvProfitTargetPercent / 100) - otherCosts
  // Effective SDLT rate on the current purchase (used to back out land £).
  const sdltEffectiveRate =
    acquisitionPrice > 0 ? acquisitionSDLT / acquisitionPrice : 0
  const residualLandValue = Math.max(
    0,
    rlvAcqTotalTarget / (1 + sdltEffectiveRate),
  )
  const landPremiumOverAsk = residualLandValue - acquisitionPrice

  // ── 13 · Cost stack (ordered) ───────────────────────────
  const stack: Array<{ label: string; amount: number }> = [
    { label: "Acquisition", amount: acquisitionTotal },
    { label: "Construction", amount: constructionTotal },
    { label: "Professional Fees", amount: professionalFeesTotal },
    { label: "Planning Obligations", amount: planningObligationsTotal },
    { label: "Finance", amount: financeCostTotal },
    { label: "Exit / Sales", amount: exitCostsTotal },
  ]
  const tdcDenom = totalDevelopmentCost > 0 ? totalDevelopmentCost : 1
  const costStack: DevelopmentCostLine[] = stack.map((s) => ({
    label: s.label,
    amount: r(s.amount),
    percentOfTDC: r2((s.amount / tdcDenom) * 100),
  }))

  // ── 14 · Viability flags ────────────────────────────────
  const flags: DevelopmentFlag[] = []
  if (profitOnCost < 15) {
    flags.push({
      severity: "danger",
      message: `Profit on cost is ${profitOnCost.toFixed(1)}% — below the 15% viability floor lenders expect.`,
    })
  } else if (profitOnCost < 20) {
    flags.push({
      severity: "warn",
      message: `Profit on cost is ${profitOnCost.toFixed(1)}% — below the 20% RICS blue-book benchmark; tight margin.`,
    })
  }
  if (ltgdv > 75) {
    flags.push({
      severity: "danger",
      message: `LTGDV is ${ltgdv.toFixed(1)}% — most dev lenders cap at 70%. Funding package unlikely.`,
    })
  } else if (ltgdv > 70) {
    flags.push({
      severity: "warn",
      message: `LTGDV is ${ltgdv.toFixed(1)}% — at the upper end of lender appetite.`,
    })
  }
  if (contingencyPct < 5) {
    flags.push({
      severity: "warn",
      message: `Construction contingency is ${contingencyPct.toFixed(1)}% — 10% is the market-standard buffer.`,
    })
  }
  if (residualLandValue < acquisitionPrice && acquisitionPrice > 0) {
    flags.push({
      severity: "warn",
      message: `Residual land value (£${r(residualLandValue).toLocaleString()}) is below your purchase price (£${r(acquisitionPrice).toLocaleString()}) — you're paying a premium to land the site.`,
    })
  }
  const affordableHousingTriggered = totalUnits >= 10
  if (affordableHousingTriggered && affordablePct === 0) {
    flags.push({
      severity: "warn",
      message: `Scheme has ${totalUnits} units — 10+ typically triggers affordable housing provision (NPPF + Local Plan). No provision currently modelled.`,
    })
  }
  if (totalUnits === 0 || totalGIA === 0) {
    flags.push({
      severity: "info",
      message:
        "Add at least one unit row with size and sale price to produce a full appraisal.",
    })
  }
  if (financeTermMonths < 12) {
    flags.push({
      severity: "info",
      message: `Finance term is ${financeTermMonths} months — most dev facilities are 12–24 months. Confirm this is realistic for your build programme.`,
    })
  }

  // ── 15 · Deal score ─────────────────────────────────────
  // 0-100, heavily weighted on profit-on-cost + LTGDV headroom.
  let score = 0
  // Profit on cost (max 50)
  score += Math.min(50, Math.max(0, profitOnCost * 2)) // 25% → 50 pts
  // Profit on GDV (max 15)
  if (profitOnGDV >= 20) score += 15
  else if (profitOnGDV >= 15) score += 10
  else if (profitOnGDV >= 12) score += 5
  // LTGDV headroom (max 15)
  if (ltgdv > 0 && ltgdv < 60) score += 15
  else if (ltgdv < 65) score += 10
  else if (ltgdv < 70) score += 5
  else if (ltgdv >= 75) score -= 10
  // Contingency discipline (max 10)
  if (contingencyPct >= 10) score += 10
  else if (contingencyPct >= 5) score += 5
  // Residual land premium / margin of safety (max 10)
  if (landPremiumOverAsk > 0 && acquisitionPrice > 0) {
    const premiumRatio = landPremiumOverAsk / acquisitionPrice
    if (premiumRatio >= 0.10) score += 10
    else if (premiumRatio >= 0.05) score += 5
  } else if (landPremiumOverAsk < 0) {
    score -= 5
  }
  // Flag deductions
  const dangerCount = flags.filter((f) => f.severity === "danger").length
  score -= dangerCount * 10
  score = Math.max(0, Math.min(100, Math.round(score)))

  let dealScoreLabel: string
  if (score >= 85) dealScoreLabel = "Excellent"
  else if (score >= 70) dealScoreLabel = "Good"
  else if (score >= 55) dealScoreLabel = "Fair"
  else if (score >= 35) dealScoreLabel = "Weak"
  else dealScoreLabel = "Poor"

  // ── 16 · Assemble result ────────────────────────────────
  return {
    // Unit mix
    totalUnits,
    totalGIA: r(totalGIA),
    totalGDV: r(totalGDV),
    avgGDVPerUnit: r(avgGDVPerUnit),
    avgGDVPerM2: r(avgGDVPerM2),
    unitLines: unitLines.map((u) => ({
      ...u,
      avgSizeM2: r(u.avgSizeM2),
      salePricePerUnit: r(u.salePricePerUnit),
      gdv: r(u.gdv),
    })),

    // Acquisition
    acquisitionPrice: r(acquisitionPrice),
    acquisitionSDLT: r(acquisitionSDLT),
    acquisitionLegal: r(acquisitionLegal),
    acquisitionSurvey: r(acquisitionSurvey),
    acquisitionTotal: r(acquisitionTotal),
    sdltRateTypeUsed,

    // Construction
    constructionBase: r(constructionBase),
    constructionAbnormals: r(constructionAbnormals),
    constructionContingency: r(constructionContingency),
    constructionTotal: r(constructionTotal),
    buildCostPerM2Used: r(buildCostPerM2Used),

    // Professional fees
    feeArchitect: r(feeArchitect),
    feeStructural: r(feeStructural),
    feeQS: r(feeQS),
    feePM: r(feePM),
    feePlanningConsultant: r(feePlanningConsultant),
    feeBuildingControl: r(feeBuildingControl),
    feeWarranty: r(feeWarranty),
    professionalFeesTotal: r(professionalFeesTotal),

    // Planning obligations
    cilTotal: r(cilTotal),
    s106Total: r(s106Total),
    affordableHousingDiscount: r(affordableHousingDiscount),
    buildingRegsFee: r(buildingRegsFee),
    planningObligationsTotal: r(planningObligationsTotal),

    // Exit
    salesAgentFee: r(salesAgentFee),
    salesLegalTotal: r(salesLegalTotal),
    marketingTotal: r(marketingTotal),
    exitCostsTotal: r(exitCostsTotal),

    // Finance
    financeFacilityLoan: r(financeFacilityLoan),
    financeDay1Drawdown: r(financeDay1Drawdown),
    financeArrangementFee: r(financeArrangementFee),
    financeExitFee: r(financeExitFee),
    financeMonitoringTotal: r(financeMonitoringTotal),
    financeInterest: r(financeInterest),
    financeCostTotal: r(financeCostTotal),
    financeTermMonths,
    financeRateUsed,
    financeRolledUp,

    // Totals
    totalCostExFinance: r(totalCostExFinance),
    totalDevelopmentCost: r(totalDevelopmentCost),
    costStack,

    // Profit
    grossProfit: r(grossProfit),
    profitOnGDV: r2(profitOnGDV),
    profitOnCost: r2(profitOnCost),

    // Leverage
    equityRequired: r(equityRequired),
    peakFunding: r(peakFunding),
    ltgdv: r2(ltgdv),
    ltc: r2(ltc),

    // Returns
    roe: r2(roe),
    annualisedROI: r2(annualisedROI),
    irr: r2(irr),

    // RLV
    residualLandValue: r(residualLandValue),
    landPremiumOverAsk: r(landPremiumOverAsk),
    rlvProfitTargetPercent,

    // Viability
    flags,
    affordableHousingTriggered,
    dealScore: score,
    dealScoreLabel,
  }
}
