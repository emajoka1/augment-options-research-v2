# MC Command Contract (Schema-Lock)

This file defines required fields for `/mc prove_trade_ready` and `/mc why_no_candidates` diagnostics.

## `scripts/mc_command.py --json` required keys

Top-level required:
- `timestamp`
- `trace_ids` (`snapshot_id`, `brief_id`, `mc_id`)
- `data_status`, `data_source`, `action_state`, `final_decision`
- `spot_integrity` (`ref_source`, `ref_spot`, `delta`, `max_delta`, `ok`)
- `mc_provenance` (`options_mc_source_mode`, `options_mc_source_file`, `generated_at`, `model`, `n_batches`, `paths_per_batch`, `n_total_paths`, `computed_n_total_paths`, `assumptions_n_paths`, `counts_consistent`, `source_stale`, `base_seed`, `crn_scope`)
- `trade_ready_rule` (`r_structural`, `r_structural_source`, `ev_mean_R`, `ev_seed_p5_R`, `ev_stress_mean_R`, `pl_p5_R`, `cvar_worst_R`, `stress_delta_ev_mean_R`, `pass`, `failures`)
- `raw`

No-candidates reason path:
- `raw["TRADE BRIEF"]["NoCandidatesReason"]` (when present)

Backward-compat aliases:
- `traceIds` -> `trace_ids`
- `spotIntegrity` -> `spot_integrity`
- `mcProvenance` -> `mc_provenance`
- `tradeReadyRule` -> `trade_ready_rule`

## `scripts/mc_why.py` diagnostics contract
Must print lines containing:
- `source_stale=` in MC risk metrics section
- `Warning: options-MC source is stale` when stale is true

