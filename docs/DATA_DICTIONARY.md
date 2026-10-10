# Data dictionary

All money fields with `_usd` are U.S. dollars unless a source file explicitly states another currency. A return or rate of `0.05` means 5%; plotting scripts multiply by 100 for percentage points. Bitcoin quantities are in BTC. Basic common shares include Class A and Class B; this is not an assumed-diluted denominator.

## Search identification and settings

| Field | Meaning |
|---|---|
| `job_id` | Deterministic identifier for a source template and search recipe. |
| `base_id` | Initial-comparison case from which the source configuration was selected. |
| `window` | Historical Bitcoin window start, not the corporate opening date. |
| `shape` | `historical` or its endpoint-matched `smooth_matched` counterpart. |
| `premium` | Inherited valuation setting: compression, persistence, or expansion. The valuation-axis coordinate overrides its terminal factor. |
| `policy` | Reference common-issuance rule or adaptive Bitcoin-per-share rule; initial comparisons also include a principal-buffer rule. |
| `regime` | Open, capitalization-constrained (`capacity`), or drawdown-closure financing access. |
| `permission` | Restricted or flexible general use of designated reserves. The reserve floor remains a separate requirement. |
| `timing` | Immediate settlement for original-stop attribution; prefunded T+1 settlement for the main feasibility searches. |
| `axis` | Condition varied: valuation, bitcoin, capacity, or sale_authority; `none` for STRC configurations. |
| `coordinate` | Axis value. Valuation and Bitcoin are terminal/opening factors; capacity is a baseline scaling factor; sale_authority is cumulative gross USD authorization. STRC jobs use a dummy zero coordinate. |
| `strc_scale` | 0, 0.5, or 1 of the new STRC program. Existing STRC remains. |
| `future_strc_rate` | Conditional future annual rate; declared opening payments are retained. |

## Outcome and diagnostic fields

| Field | Meaning |
|---|---|
| `payments` | Declared schedule completed under the supplied permissions. |
| `funded` | Payments complete and reserve floor met at every corporate event. |
| `nominal_value` | Funded and terminal common quote at least its opening quote. |
| `annual_5pct` | Funded and common return at least `1.05**(457/365.25)-1`. |
| `bitcoin_per_share` | Funded and closing Bitcoin per basic share at least its opening value. |
| `common_return` | Conditional terminal/opening common-quote return. Missing for incomplete paths. |
| `bitcoin_per_share_change` | Terminal/opening Bitcoin per basic share minus one; missing for incomplete paths. |
| `event_common_drawdown` | Nonpositive peak-to-trough common-quote change measured at corporate events. Figure 2 shows its positive loss magnitude. |
| `common_gross_usd`, `strc_gross_usd` | Gross issuance proceeds before fees. |
| `annualized_strc_distribution_usd` | Terminal run-rate distribution obligation on opening and new STRC. |
| `configuration_sha256`, `result_sha256` | Exact reconstruction and replay hashes. |
| `independent_checks`, `maximum_arithmetic_error` | Original evaluation's audit count and maximum absolute residual, in the units of each checked identity. |

## Boundaries and missing values

`required_conditions.csv` has one row per job/target. `lowest_feasible_tested` is the lowest passing tested coordinate, not a proven global minimum. `lower_failing_coordinate` is its neighboring failing witness where present. `boundary_status` distinguishes an interior bracket, success at the search-domain floor, and no feasible tested point. Missing requirements mean no passing point in the stated domain. They do not imply impossibility beyond it.

`observed_reversal` records a pass-to-fail transition as the coordinate increases. `feasible_bands.csv` retains all observed passing bands. Narrow unsampled bands may remain unresolved. Scenario frequencies and displayed ranges have no assigned probability interpretation.

Paired STRC effects subtract the no-new-STRC case with the same source case and future rate. `jointly_funded` requires both members to complete payments and maintain reserves. These comparisons keep the common channel unchanged; they do not impose an equal total financing budget.
