"""Options Alpha: a deterministic options decision workflow with a bounded model.

The continuous runtime is `options_alpha_lab.worker`; `options_alpha_lab.agent`
runs one-shot cycles; `options_alpha_lab.api` serves the read-only presentation
API. The original hackathon interaction experiment lives in `orchestrator`
(`run_experiment`) with `models`, `agents` and `risk`, and is imported from
there by name: it is no longer what importing the package gives you (`CSA-003`).
"""
