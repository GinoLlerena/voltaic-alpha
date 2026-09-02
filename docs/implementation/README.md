# Implementation documents

Design, build, and operations records. These are the working documents behind
the system; they are not hackathon submission artifacts.

The submission-facing documents stay one level up in [`docs/`](../):
the [submission checklist](../options_alpha_submission_checklist_v0_1.md), the
[submission narrative](../options_alpha_submission_narrative_v0_1.md), the
[requirements traceability matrix](../options_alpha_requirements_traceability_v0_1.md),
and the [video script](../options_alpha_video_script_v0_1.md).

## Design and specification

| Document | What it holds |
|---|---|
| [Trading design](options_alpha_trading_design_v0_1.md) | Strategy, sizing, and the trading rules the deterministic code owns |
| [Architecture slice](options_alpha_architecture_slice_v0_1.md) | Component boundaries, ports, and where model authority ends |
| [H0 signal spec](options_alpha_h0_signal_spec_v0_1.md) | The null-hypothesis setup definition |
| [Exit policy review](options_alpha_exit_policy_review_v0_1.md) | Exit trigger precedence and position lifecycle |
| [Frontend design](options_alpha_frontend_design_v0_1.md) | Five-view judge-facing dashboard specification |

## Build plans

| Document | What it holds |
|---|---|
| [Bot implementation plan](options_alpha_bot_implementation_plan_v0_1.md) | Phased build plan and skill dispositions |
| [Strategy improvement plan](options_alpha_strategy_improvement_implementation_plan_v0_1.md) | Post-hackathon strategy fixes, deliberately deferred |
| [Multi-position scaling handoff](options_alpha_multi_position_scaling_handoff_v0_1.md) | Scaling from one position to many |
| [Task 1: manage many](options_alpha_multi_position_task_1_manage_many_v0_1.md) | Management path for multiple positions |
| [Task 2: portfolio entry](options_alpha_multi_position_task_2_portfolio_entry_v0_1.md) | Entry path under a portfolio cap |
| [Pending requirements handoff](options_alpha_pending_requirements_dev_handoff_v0_1.md) | Closing the remaining hackathon requirement rows |

## Operations and evidence

| Document | What it holds |
|---|---|
| [Deployment runbook](options_alpha_deployment_runbook_v0_1.md) | Hosts, systemd units, watchdog, backup, and recovery procedures |
| [Validation test suite](options_alpha_agents_validation_test_suite.md) | The gates and what each one proves |
| [Phase 0 event cut line](options_alpha_phase0_event_cut_line_v0_1.md) | What existed before the event, and the findings register |
| [Reuse ledger](options_alpha_reuse_ledger.md) | Pre-existing code and its provenance |
