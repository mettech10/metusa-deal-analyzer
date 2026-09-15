"""
Section 24 / ITTOIA 2005 ss272A, 274A, 274AA.

Finance costs on residential property are not deductible from property profits
for individuals. Relief is a tax reducer at the property basic rate (20% in
2026/27) on the statutory lower-of-three amount, with unused finance costs
carried forward.

This is not "20% of mortgage interest if you are a higher-rate taxpayer".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ltd_co.money import ZERO, clamp0, money
from ltd_co.rates import RatePack


@dataclass(frozen=True)
class Section24Result:
    rental_income: Decimal
    allowable_non_finance_expenses: Decimal
    finance_costs_current_year: Decimal
    finance_costs_brought_forward: Decimal
    property_losses_brought_forward: Decimal
    property_profit_before_losses: Decimal
    property_profit: Decimal  # after s118 losses; not below zero
    property_loss_carried_forward: Decimal
    relievable_amount: Decimal  # s274A: current + b/f finance costs
    limb_finance_costs: Decimal
    limb_property_profits: Decimal
    limb_adjusted_total_income: Decimal
    binding_limb: str  # finance_costs | property_profits | adjusted_total_income
    actual_amount: Decimal  # AA in s274AA(5)
    reducer_rate: Decimal
    tax_reducer: Decimal
    finance_costs_carried_forward: Decimal
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        from ltd_co.money import to_float

        return {
            "rentalIncome": to_float(self.rental_income),
            "allowableNonFinanceExpenses": to_float(self.allowable_non_finance_expenses),
            "financeCostsCurrentYear": to_float(self.finance_costs_current_year),
            "financeCostsBroughtForward": to_float(self.finance_costs_brought_forward),
            "propertyLossesBroughtForward": to_float(self.property_losses_brought_forward),
            "propertyProfitBeforeLosses": to_float(self.property_profit_before_losses),
            "propertyProfit": to_float(self.property_profit),
            "propertyLossCarriedForward": to_float(self.property_loss_carried_forward),
            "relievableAmount": to_float(self.relievable_amount),
            "lowerOfThree": {
                "financeCosts": to_float(self.limb_finance_costs),
                "propertyProfits": to_float(self.limb_property_profits),
                "adjustedTotalIncome": to_float(self.limb_adjusted_total_income),
                "bindingLimb": self.binding_limb,
            },
            "actualAmount": to_float(self.actual_amount),
            "reducerRate": to_float(self.reducer_rate, places=4),
            "taxReducer": to_float(self.tax_reducer),
            "financeCostsCarriedForward": to_float(self.finance_costs_carried_forward),
            "statute": {
                "restriction": "ITTOIA 2005 s272A",
                "entitlement": "ITTOIA 2005 s274A",
                "calculation": "ITTOIA 2005 s274AA",
                "lossRelief": "ITA 2007 s118",
            },
            "notes": list(self.notes),
        }


def adjusted_total_income(
    *,
    net_income: Decimal,
    savings_income: Decimal,
    dividend_income: Decimal,
    personal_allowance: Decimal,
) -> Decimal:
    """
    ITTOIA 2005 s274AA(6):
      Step 1  net income (ITA 2007 s23 Step 2)
      Step 2  exclude savings income and dividend income
      Step 3  deduct personal (and similar Step 3) allowances
    """
    after_exclude = money(net_income) - clamp0(savings_income) - clamp0(dividend_income)
    if after_exclude < 0:
        after_exclude = ZERO
    ati = after_exclude - clamp0(personal_allowance)
    return ati if ati > 0 else ZERO


def _binding_limb(
    finance: Decimal,
    profits: Decimal,
    ati: Decimal,
) -> str:
    """
    First-match on ties, matching how GOV.UK examples narrate the lowest figure:
    finance costs, then property profits, then ATI.
    """
    lowest = min(finance, profits, ati)
    if finance == lowest:
        return "finance_costs"
    if profits == lowest:
        return "property_profits"
    return "adjusted_total_income"


def compute_section24(
    *,
    rental_income: Decimal,
    allowable_non_finance_expenses: Decimal,
    finance_costs: Decimal,
    packs: RatePack,
    other_non_savings_income: Decimal = ZERO,
    savings_income: Decimal = ZERO,
    dividend_income: Decimal = ZERO,
    finance_costs_brought_forward: Decimal = ZERO,
    property_losses_brought_forward: Decimal = ZERO,
    personal_allowance: Decimal | None = None,
) -> Section24Result:
    """
    Single UK residential property business, individual landlord.

    Property profit is computed WITHOUT deducting finance costs (s272A).
    Losses b/f under ITA 2007 s118 reduce profits before the profits limb.
    """
    notes: list[str] = []
    rent = clamp0(rental_income)
    opex = clamp0(allowable_non_finance_expenses)
    interest = clamp0(finance_costs)
    bf_fin = clamp0(finance_costs_brought_forward)
    bf_loss = clamp0(property_losses_brought_forward)

    profit_before_losses = money(rent - opex)
    loss_cf = ZERO
    if profit_before_losses < 0:
        loss_cf = money(-profit_before_losses)
        profit_after_current = ZERO
        notes.append("Current-year property loss: profits limb is £0; finance costs carry forward.")
    else:
        profit_after_current = profit_before_losses

    # s118: losses b/f reduce profits; surplus loss remains available.
    if bf_loss > profit_after_current:
        property_profit = ZERO
        loss_cf = money(loss_cf + (bf_loss - profit_after_current))
        notes.append("Property losses brought forward absorbed all current-year profits (ITA 2007 s118).")
    else:
        property_profit = money(profit_after_current - bf_loss)

    relievable = money(interest + bf_fin)
    limb_finance = relievable
    limb_profits = property_profit

    # L in s274AA(2) = min(relievable, adjusted profits) for a non-estate business.
    L = limb_finance if limb_finance < limb_profits else limb_profits

    other_ns = clamp0(other_non_savings_income)
    savings = clamp0(savings_income)
    dividends = clamp0(dividend_income)
    net_income = money(other_ns + property_profit + savings + dividends)

    if personal_allowance is None:
        from ltd_co.income_tax import personal_allowance as pa_fn

        pa = pa_fn(net_income, packs)
    else:
        pa = clamp0(personal_allowance)

    ati = adjusted_total_income(
        net_income=net_income,
        savings_income=savings,
        dividend_income=dividends,
        personal_allowance=pa,
    )

    # s274AA(3): if S > ATI, AA = ATI/S * L. One business ⇒ S = L ⇒ AA = ATI.
    S = L
    if S > ati:
        if S == 0:
            actual = ZERO
        else:
            actual = money(ati)  # ATI/S * L with S=L
        notes.append(
            "ATI is below L (s274AA(3)): reducer is based on adjusted total income, not full finance costs."
        )
    else:
        actual = L

    binding = _binding_limb(limb_finance, limb_profits, ati)
    # After ATI cap, the actual amount may be ATI even if binding_limb from min()
    # already selected ATI. If L was used, binding is finance or profits.

    reducer_rate = packs.income_tax.property_finance_reducer_rate
    tax_reducer = money(actual * reducer_rate)
    carried = money(relievable - actual)
    if carried < 0:
        carried = ZERO

    notes.append(
        "Reducer is a tax reduction (ITA 2007 s23 Step 6), not a deduction from profits. "
        "It cannot create a repayment."
    )

    return Section24Result(
        rental_income=rent,
        allowable_non_finance_expenses=opex,
        finance_costs_current_year=interest,
        finance_costs_brought_forward=bf_fin,
        property_losses_brought_forward=bf_loss,
        property_profit_before_losses=profit_before_losses if profit_before_losses > 0 else ZERO,
        property_profit=property_profit,
        property_loss_carried_forward=loss_cf,
        relievable_amount=relievable,
        limb_finance_costs=limb_finance,
        limb_property_profits=limb_profits,
        limb_adjusted_total_income=ati,
        binding_limb=binding,
        actual_amount=actual,
        reducer_rate=reducer_rate,
        tax_reducer=tax_reducer,
        finance_costs_carried_forward=carried,
        notes=tuple(notes),
    )
