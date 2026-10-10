# Dated financing contract — v0.4.0

The contribution and minimum specification are in `FINANCING_SPECIFICATION.md`. Engine 0.4.0 is `treasury_company/growth.py`; engine 0.3.0 is unchanged. Its debt, accrual, reserve-use, sale-purpose and joint-feasibility rules remain documented in `MODEL_CONTRACT_v0.3.0.md`. The following rules replace that version's restrictions on new preferred issuance and Bitcoin purchases.

## State and valuation

The opening adds `strc_shares`. STRC's liquidation claim equals shares times the supplied preference; accrued dividends remain separate. The dividend stated amount is $100. Other opening assets, shares, claims and unallocated payables remain unchanged.

Residual backing K is Bitcoin value plus liquid/restricted cash assets plus net operating value, less financial claims and accrued distributions. The common quote is mK/N when K is positive, where m is a supplied multiple and N is basic common shares. Nonpositive K makes this mapping undefined, not an automatic default or a zero common price. The reserve remains a designation within liquid assets.

## Event order and information

1. Accrue unpaid distributions and record operating receipts.
2. Apply the current supplied liquidation preference to all STRC shares.
3. Execute permitted requested STRC issuance; add cash, shares, claim and generated future dividends.
4. Update the reserve target for current annualized STRC distributions.
5. Identify payments and funding need. Price and execute common issuance from the current state after STRC issuance.
6. Use permitted Bitcoin sales and Treasury liquidation for residual needs.
7. Stop before joint settlement if unsupported, retaining funding already raised and all new claims. Otherwise settle atomically and replenish the reserve designation.
8. Apply any separately authorized common repurchase, excluding events with common or STRC issuance.
9. Purchase Bitcoin within cash, reserve, buffer, allocation and execution bounds, excluding events with any Bitcoin sale or common repurchase.
10. Record states, decisions, commitments, valuations and joint-support diagnostics.

Current actions do not inspect future Bitcoin prices, premiums or financing capacities. Templates encode dates and supplied dividend-rate scenarios; a future rate affects accrual only in its specified period. Tests change future prices, capacities and rates while preserving earlier states and transactions.

## Common ATM

`common_program_target_gross_usd` is the desired total event issue, including funds for current needs. It is not added again to the funding requirement. Gross issuance is the greater of the permitted program target and gross funding need, capped by current market capacity and remaining cumulative gross authorization.

Execution price is the current conditional quote times one minus the discount. New shares equal gross proceeds divided by price; cash receives gross proceeds times one minus the fee. `common_access_min_multiple` screens the current multiple. `common_growth_min_net_premium` screens net execution proceeds per new share relative to pre-issue backing per share.

`common_fund_cash_shortfalls=False` disables extra funding issuance in equal-capital controls. The `liquidity` mode otherwise permits funding issuance when the growth screen fails; `accretive_only` requires net execution price at least backing per share. These are scenario policies, not company mNAV thresholds.

## STRC

Gross issuance is the minimum of the management target, market capacity and remaining authorization, conditional on the execution-price band and the optional positive-backing screen. Zero capacity gives zero issuance even at $100. Authorizations are cumulative gross sale dollars, not stated amount or net receipts.

New shares equal gross proceeds divided by execution price. Cash increases by net proceeds after fees; the preferred claim increases by new shares times the supplied preference. Common shares do not change.

The calendar has contiguous full semimonthly periods with record date, nominal accrual end, adjusted cash date and annual rate. It starts at opening and extends beyond the horizon. Original-share payments must cover each period. Opening declared credits remain fixed; other original-share amounts must match their period rate. Missing periods are rejected.

STRC offers execute on business-day regular record dates before the cutoff. Each issue generates new payments for that and subsequent record dates: new shares times $100 times annual rate divided by 24. The first payment follows issuance. New shares never inherit opening credits or same-date dividends. Generated payments beyond the horizon remain recorded; preferred claims and shares remain outstanding at the terminal mark.

Linear economic accrual follows the inherited ledger. A business-day payment delay does not extend accrual. This restricted issuance calendar does not implement arbitrary first-period ATM exceptions or actual settlement lags. Accepted paths assume all STRC cash dividends declared and paid; failure does not generate an invented restructuring or arrears path.

Preference is a supplied path with a $100 floor, not an estimate from sparse execution quotes. Changes apply to all shares. A higher preference alone does not increase the regular dividend, which uses stated amount.

## Reserve and allocation

For current STRC shares Q and rate r, and opening Q0 and r0:

```text
effective_floor = max(0, base_floor + reserve_months/12 * 100*(Q*r - Q0*r0))
```

The comparisons use 12 months; a fixed-reserve sensitivity uses zero. Other base-floor assumptions and reserve-use restrictions remain explicit. Failure to reach the target is a policy failure, not automatically an unpaid contractual obligation.

Available purchase cash is the nonnegative minimum of cash and liquid assets less the reserve designation and unreserved cash buffer. Desired spending equals `purchase_fraction` times current net financing receipts. With `deploy_existing_surplus_cash=True`, its base instead becomes all available purchase cash. The execution cap is in Bitcoin units; cost is quantity times price times one plus the purchase-cost rate. Unspent cash carries forward.

The cash buffer protects against discretionary purchases but can fund commitments. It does not compel issuance to refill it or enter the primary joint criterion. The default does not automatically deploy older retained cash at a later zero-financing event; the separate existing-cash policy enables that choice.

## Records and verification

Each result retains the exact configuration and digest, full journal, every event state, initial mark, new-share payments, per-event financing gates/requests/capacities/executions, support assessment and unprocessed tail. Closed price gates, zero demand and exhausted authorization remain distinguishable. Purchases, sales and net accumulation are separate outputs.

Journal reconciliation reconstructs every atomic prefix. `check_financing.py` independently checks proceeds, share increments, claims, costs, authorizations, cash protection, absence of Bitcoin round trips, and generated dividends against eligible issued shares. Hand-calculated tests check fees, per-share outcomes, dividend timing, missing schedules and no-look-ahead.

The primary joint criterion retains its earlier meaning: payments, reserve tests and the equity outcome must hold on the same complete path. Accounting checks do not establish bankruptcy, optimal policy, investor demand, legal compliance for every instrument, or forecast accuracy.
