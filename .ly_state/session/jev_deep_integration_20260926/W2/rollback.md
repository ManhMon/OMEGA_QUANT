# W2 rollback

Set `jev_influence=0` on regime overlay and `influence=0` on alpha tilt. Re-run the focused regression suite; both paths use the quantitative baseline and skip classification. Existing deterministic risk enforcement remains in place.

If either registered-domain classification fails, keep the quantitative baseline. The alpha profile requires a separate `alpha_disagreement` decision before tilting; missing or failed second decision also keeps baseline.
