# phase2-v2 vs phase2

| Model | Level | Before | After | Change (pts) | 95% CI | Steps capped before | after |
|---|---|---|---|---|---|---|---|
| Haiku | docs | 99.5 | 99.5 | +0.0 | -1.6 to +1.6 | 0.0% | 0.0% |
| Haiku | full | 93.8 | 95.8 | +2.1 | -1.6 to +5.7 | 0.0% | 0.0% |
| Gemma | docs | 68.2 | 66.7 | -1.6 | -13.0 to +9.9 | 21.9% | 20.8% |
| Gemma | full | 83.3 | 87.5 | +4.2 | -3.1 to +12.0 | 11.5% | 7.8% |

Questions that changed (share of runs correct):

- Gemma docs `h_ss_share`: 1.00 to 0.00
- Gemma docs `h_top_deployment`: 1.00 to 0.00
- Gemma docs `traces_sep`: 1.00 to 0.00
- Gemma docs `x_activation_q4_25`: 1.00 to 0.00
- Gemma docs `x_days_to_activate`: 1.00 to 0.00
- Gemma docs `x_ent_traces_q3`: 1.00 to 0.00
- Gemma full `x_ent_grr_sep`: 1.00 to 0.33
- Gemma full `x_nrr_sep`: 1.00 to 0.33
- Gemma docs `x_region_arpc`: 0.67 to 0.00
- Gemma docs `x_sh_trace_share`: 0.67 to 0.00
- Gemma docs `x_top_category_q3`: 0.67 to 0.00
- Haiku docs `x_days_upgrade`: 1.00 to 0.67
- Haiku full `ss_churn_q3`: 1.00 to 0.67
- Gemma docs `x_new_logo_arr_q3`: 1.00 to 0.67
- Gemma full `x_median_ent_arr`: 1.00 to 0.67
- Gemma full `x_plus_10_seats`: 1.00 to 0.67
- Gemma full `x_sh_trace_share`: 1.00 to 0.67
- Haiku full `x_nb_arr_2026`: 0.67 to 0.33
- Gemma docs `x_arr_urgent_q3`: 0.33 to 0.00
- Gemma docs `x_nb_arr_2026`: 0.33 to 0.00
- Gemma full `ent_churn_2026`: 0.33 to 0.00
- Gemma full `ss_churn_q3`: 0.33 to 0.00
- Haiku docs `x_emea_growth`: 0.67 to 1.00
- Gemma docs `avg_ent_arr`: 0.67 to 1.00
- Gemma docs `ss_billed_2025`: 0.67 to 1.00
- Gemma docs `x_ent_tickets_q3`: 0.67 to 1.00
- Gemma docs `x_plus_events_per_dau`: 0.67 to 1.00
- Gemma full `paid_rate_2025`: 0.67 to 1.00
- Gemma full `x_avg_dau_sep`: 0.67 to 1.00
- Gemma full `x_urgent_hours_q3`: 0.67 to 1.00
- Haiku full `h_arr_change_ytd`: 0.00 to 0.67
- Haiku full `paying_ent_sep26`: 0.00 to 0.67
- Gemma docs `stale_active`: 0.00 to 0.67
- Gemma full `x_days_upgrade`: 0.00 to 0.67
- Gemma full `x_plus_events_per_dau`: 0.00 to 0.67
- Haiku full `x_avg_plus_seats_q3`: 0.33 to 1.00
- Gemma docs `top_region`: 0.33 to 1.00
- Gemma docs `x_best_nn_month`: 0.33 to 1.00
- Gemma docs `x_ent_invoiced_2025`: 0.33 to 1.00
- Gemma docs `x_expansion_arr_q3`: 0.33 to 1.00
- Gemma docs `x_paid_given_active`: 0.33 to 1.00
- Gemma docs `x_traces_mom`: 0.33 to 1.00
- Gemma full `x_avg_plus_seats_q3`: 0.33 to 1.00
- Gemma full `x_churned_arr_q3`: 0.33 to 1.00
- Gemma docs `x_contract_arr_2025`: 0.00 to 1.00
- Gemma docs `x_days_upgrade`: 0.00 to 1.00
- Gemma full `paying_ent_sep26`: 0.00 to 1.00
- Gemma full `x_upgraded_count`: 0.00 to 1.00