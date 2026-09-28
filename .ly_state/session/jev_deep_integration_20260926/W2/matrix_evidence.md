# W2 adversarial evidence

Focused checks: `python -m pytest tests/test_jev_regime_alpha_weighting.py -q`.
Malformed numeric metrics and unknown regime IDs reject; future evidence, provider timeout and unsupported disagreement fall back; disabled controls preserve baseline. No checkpoint, network, URL routing, CLI, publication lock, credential, or decision-gate subsystem changed by W2; those dimensions require independent upstream evidence rather than claims from these unit tests.

Remediation: `test_real_classifier_boundary_for_both_domains` reaches actual `classify_jev` domain validation with provider fault injection; `test_hmm_early_features_prefix_invariant` compares early features after a future volatility shock. Classifier provider failure preserves baseline.

F-003: `test_historical_regime_classifier_cache_miss_disables_provider` reaches actual `classify_jev` with historical cutoff and `cache_only`. Cache miss preserves baseline; injected provider constructor fails test if called. Historical cached decisions must predate their decision cutoff under schema v2; no historical decision is synthesized from a live provider.
