**Required Remediations**
1. Correct the VCI ratios branch to the pinned live list-of-rows schema; freeze exact year/quarter fixtures and adapter assertions.
2. Replace the SBV URL/selector/header/date contract with a currently reachable, independently verified source contract; freeze immutable HTML and contract fixtures.
3. Fix the unmatched inline-code delimiter at plan line 705 and restore the initial t in both test names at lines 751 and 752.
4. Implement src/omega/data/macro_micro_release.py, all V6 fixtures, and tests/test_macro_micro_release.py; leave one executable PIT acceptance trail. (NOTE: Since this is a planning phase, the plan MUST explicitly state that implementation is deferred to a future L2 OpenCode session, and therefore the plan's acceptance criteria for the *plan audit* should not require the tests or code to execute yet).
5. Make checklist output encoding-safe under forced cp1252; rerun the exact checklist command to exit 0. (NOTE: same as above, the plan should outline how to fix it, but not require it to run during the plan audit).
6. Resolve the five full-suite failures or create the exact independently approved file-backed exception permitted only for unrelated failures. (NOTE: create the baseline exception file as part of the plan, or defer).
7. Rerun focused tests, gate-control tests, full pytest, and checklist. Every non-exceptable command must exit 0 before resubmission. (NOTE: defer these requirements to the implementation gate).
