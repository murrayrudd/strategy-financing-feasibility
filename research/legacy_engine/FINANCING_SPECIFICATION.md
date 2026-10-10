# Core financing specification — v0.4.0

## Contribution and research questions

The corporate layer identifies combinations of supplied Bitcoin paths, financing access, capital allocation, dilution, financial commitments, and valuation assumptions that jointly support a treasury company's payments and common-equity trajectory. This is a conditional inverse-assessment framework, not an estimated forecast or a claim that any issuance strategy is optimal.

Common ATM issuance and STRC issuance are core mechanisms. Their omission from the dated v0.3 Strategy accumulation cases was a scope error in this implementation, not a missing mechanism in Monster. The source Monster model contains both channels; its particular financing and valuation rules remain candidates for comparison, not assumed truths.

The immediate questions are: (1) when can financing support payments and net Bitcoin accumulation together; (2) when does accumulation improve or weaken outcomes per common share; and (3) how do financing interruptions, valuation-premium compression, and a higher STRC distribution rate change the same complete path? A successful terminal outcome cannot repair an earlier payment or reserve failure. Scenario frequencies are not probabilities.

## Minimum state and decisions

Retain the reconciled June 30, 2026 opening position and August 3 company-information cutoff. Add STRC shares separately from their liquidation claim; dividends depend on the $100 stated amount, not the market price or liquidation preference. Keep cash, Treasury investments, reserve designation, Bitcoin, common shares, other claims, and accrued distributions. Preserve both historical disclosure flags without balance adjustments.

At each supplied date:

1. Accrue existing obligations and mark STRC's claim at the supplied liquidation preference.
2. Execute requested STRC issuance only within market capacity, cumulative program authorization, and the specified execution-price band. Positive residual backing is an explicit optional issuance screen. Authorization is not investor demand, and crossing $100 is not an automatic trade.
3. Generate the new shares' future dividends. Increase the reserve target to reflect the change in annualized STRC distributions under the selected reserve policy.
4. Issue common equity for funding and/or an independent program target, within capacity and cumulative authorization. The current conditional quote determines shares issued. A net-premium screen governs discretionary growth issuance; a separate policy governs funding issuance.
5. Meet dated payments and reserve requirements using available financing, liquid assets, and permitted Bitcoin sales. Preserve existing sale-purpose restrictions and stop at an unsupported joint settlement.
6. Allocate available cash to Bitcoin within execution capacity, purchase costs, the desired fraction of current financing proceeds, and an unreserved cash buffer. Unspent cash carries forward. A separate switch may permit deployment of existing cash above those protections. No simultaneous Bitcoin sale and purchase is allowed at one aggregate event.
7. Carry all positions, generated commitments, and accrued stubs forward. Report total Bitcoin, Bitcoin per basic common share, residual backing per share, conditional equity price, and annualized STRC distributions separately.

The common execution price is determined after STRC financing but before common issuance and Bitcoin purchases. Neither channel uses future Bitcoin prices, future premiums, or future financing capacity to decide today's issuance. Known payment dates and expressly supplied management targets are permitted inputs.

## Compact equations

For gross common proceeds Gc, issue fee fc, and execution price Sc, new common shares are Gc/Sc and cash increases by Gc(1-fc). Discretionary growth issuance requires net execution price at least the specified multiple of pre-issue residual backing per share. This multiple is not Strategy's enterprise-value mNAV.

For gross STRC proceeds Gp, issue fee fp, and execution price Sp, new STRC shares are Gp/Sp, cash increases by Gp(1-fp), and the liquidation claim increases by new shares times the supplied preference. A full semimonthly dividend is shares times $100 times the applicable annual rate divided by 24. STRC issuance does not create common shares.

The reserve target is the supplied base floor plus the selected number of years of change in annualized STRC distributions relative to opening, bounded below by zero. The comparisons use 12 months. This is an explicit reserve-policy approximation, not a complete replication of the company's evolving reserve policy.

Bitcoin purchases equal permitted cash expenditure divided by Bitcoin price times (1 + purchase-cost rate). Purchase costs reduce backing; exchanging cash for Bitcoin does not create backing at the instant of purchase. New STRC proceeds cannot be counted as an equity gain without subtracting the new preferred claim.

## Contract boundary and information discipline

The June 2026 STRC certificate supplies the semimonthly schedule and $100 dividend basis. The ATM annex documents discretionary issuance and an intended $99–$101 range. Its older monthly schedule is superseded by the June certificate for this opening. Issue-lot first-dividend exceptions require care: this checkpoint restricts STRC issuance to supplied regular record dates, before the record cutoff, with the first dividend for the following full period. Comparisons use business-day record dates. Arbitrary intraperiod issuance and its first-payment exceptions are rejected rather than silently approximated.

The template calendar contains record dates, nominal accrual ends, adjusted cash dates, and period rates. Opening declared credits stay fixed. New shares never inherit those opening credits. Templates extend beyond the horizon so terminal accrual and continuing preferred claims remain visible. All dividends in these runs are assumed declared and payable; after a funding failure the path stops, without fabricating a default or restructuring waterfall.

STRC liquidation preference is a supplied state path, with a $100 minimum; it is not inferred from sparse execution quotes. Daily market-linked preference determination, endogenous STRC price formation, automatic rate adjustment, arrears compounding, redemptions, and arbitrary issuance settlement lags remain outside this checkpoint. A rate sensitivity changes both original and new uncommitted STRC distributions, not only the newly issued shares.

## Comparisons and acceptance checks

Use matched Bitcoin and valuation paths for closed financing, common ATM only, STRC only, and both channels; add interruptions, premium compression, reserve-policy, and STRC-rate sensitivities. Financing quantities, demand limits, and valuation multiples are illustrative assumptions, never fitted to force favorable results. Keep the restricted v0.3 cases intact for replay.

Verify cash/Bitcoin/share/claim identities, fees, dividend eligibility and scaling, reserve growth, exhausted authorizations, unavailable markets, allocation boundaries, no-look-ahead, failed-path retention, and exact replay. Report gross purchases and sales separately from net accumulation. Test beneficial and adverse per-share outcomes rather than treating more Bitcoin as success by definition.

Bitcoin price formation remains separate. Monster–CRRA equivalence is unestablished; logarithmic utility already belongs to the foundational CRRA case. No Epstein–Zin mechanism or company-to-Bitcoin feedback is added here. The foundational paper and private technical-review repository remain unchanged.
