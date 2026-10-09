import { useEffect, useRef, useState } from 'react';
import { advancedQuantApi, strategyErrorMessage, validateStrategyRead, validateStrategyWalkRequest, validateStrategyDiagnostics, validateStrategyEquity, validateStrategyWalk } from '../api/advancedQuant';
import type { StrategyReadRequest, StrategyWalkForwardRequest, StrategyDiagnostics, StrategyEquity, StrategyWalkForward } from '../api/advancedQuant';

type ReadState = { binding: string; loading: boolean; diagnostics: StrategyDiagnostics | null; equity: StrategyEquity | null; diagnosticsError: string | null; equityError: string | null };
type WalkState = { binding: string; loading: boolean; data: StrategyWalkForward | null; error: string | null };

export function useStrategyLab(read: StrategyReadRequest, walk: StrategyWalkForwardRequest) {
  let snapshot: StrategyReadRequest | null = null, walkSnapshot: StrategyWalkForwardRequest | null = null;
  try { snapshot = validateStrategyRead(read); walkSnapshot = validateStrategyWalkRequest(walk); } catch { /* Invalid edits hide all previous results. */ }
  const binding = JSON.stringify([snapshot, walkSnapshot]), current = useRef(binding);
  current.current = binding;
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ReadState | null>(null);
  const [walkState, setWalkState] = useState<WalkState | null>(null);
  const readController = useRef<AbortController | null>(null);
  const walkController = useRef<AbortController | null>(null);
  const valid = snapshot !== null && walkSnapshot !== null;

  useEffect(() => {
    walkController.current?.abort();
    setWalkState(null);
    if (!valid) return;
    const controller = new AbortController(), request = snapshot!; readController.current = controller;
    setState({ binding, loading: true, diagnostics: null, equity: null, diagnosticsError: null, equityError: null });
    void Promise.allSettled([
      advancedQuantApi.getOverfittingDiagnostics(request.strategy_id, request.trials_tested, controller.signal, request.as_of).then((v) => validateStrategyDiagnostics(v, request)),
      advancedQuantApi.getStrategyEquity(request, controller.signal).then((v) => validateStrategyEquity(v, request)),
    ]).then(([diagnostics, equity]) => {
      if (controller.signal.aborted || current.current !== binding) return;
      const d = diagnostics.status === 'fulfilled' ? diagnostics.value : null;
      const e = equity.status === 'fulfilled' ? equity.value : null;
      const mismatch = d?.diagnostic_basis === 'PERSISTED_STRATEGY_TRIALS' && e !== null && (d.input_integrity.content_sha256 !== e.input_integrity.content_sha256 || Date.parse(d.input_integrity.effective_cutoff) !== Date.parse(e.input_integrity.effective_cutoff));
      setState({ binding, loading: false, diagnostics: mismatch ? null : d, equity: mismatch ? null : e,
        diagnosticsError: mismatch ? 'Strategy snapshots disagree. Retry.' : diagnostics.status === 'rejected' ? strategyErrorMessage(diagnostics.reason) : null,
        equityError: mismatch ? 'Strategy snapshots disagree. Retry.' : equity.status === 'rejected' ? strategyErrorMessage(equity.reason) : null });
    });
    return () => { controller.abort(); walkController.current?.abort(); };
  }, [binding, revision, valid]);

  async function runWalkForward() {
    if (!valid) return;
    walkController.current?.abort();
    const controller = new AbortController(); walkController.current = controller;
    setWalkState({ binding, loading: true, data: null, error: null });
    try {
      const data = validateStrategyWalk(await advancedQuantApi.runWalkForwardCpcv(walkSnapshot!, controller.signal), walkSnapshot!);
      if (!controller.signal.aborted && current.current === binding) setWalkState({ binding, loading: false, data, error: null });
    } catch (error) {
      if (!controller.signal.aborted && current.current === binding) setWalkState({ binding, loading: false, data: null, error: strategyErrorMessage(error) });
    }
  }

  const visible = valid && state?.binding === binding ? state : null;
  const visibleWalk = valid && walkState?.binding === binding ? walkState : null;
  return { valid, loading: valid && (!visible || visible.loading), diagnostics: visible?.diagnostics ?? null,
    equity: visible?.equity ?? null, diagnosticsError: visible?.diagnosticsError ?? null, equityError: visible?.equityError ?? null,
    walk: visibleWalk?.data ?? null, walkError: visibleWalk?.error ?? null, running: visibleWalk?.loading ?? false,
    runWalkForward, refresh: () => { readController.current?.abort(); walkController.current?.abort(); setState(null); setWalkState(null); setRevision((v) => v + 1); } };
}
