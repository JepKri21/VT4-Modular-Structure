import { useState, useCallback } from "react";

export function useHistory<T>(initial: T) {
  const [history, setHistory] = useState([initial]);
  const [idx, setIdx] = useState(0);
  const current = history[idx];

  const commit = useCallback(
    (updater: T | ((prev: T) => T)) => {
      setHistory((h) => {
        const cur = h[idx];
        const next =
          typeof updater === "function"
            ? (updater as (prev: T) => T)(cur)
            : updater;
        return [...h.slice(0, idx + 1), next];
      });
      setIdx((i) => i + 1);
    },
    [idx],
  );

  // For live drag: mutate current entry without creating new history step
  const mutate = useCallback(
    (updater: T | ((prev: T) => T)) => {
      setHistory((h) => {
        const next = [...h];
        next[idx] =
          typeof updater === "function"
            ? (updater as (prev: T) => T)(next[idx])
            : updater;
        return next;
      });
    },
    [idx],
  );

  // Finalize: snapshot current into a new history entry (used after drag)
  const snapshot = useCallback(() => {
    setHistory((h) => [...h.slice(0, idx + 1), h[idx]]);
    setIdx((i) => i + 1);
  }, [idx]);

  return {
    state: current,
    commit,
    mutate,
    snapshot,
    undo: () => setIdx((i) => Math.max(0, i - 1)),
    redo: () => setIdx((i) => Math.min(history.length - 1, i + 1)),
    canUndo: idx > 0,
    canRedo: idx < history.length - 1,
  };
}
