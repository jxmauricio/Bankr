import { useEffect, useRef, useState } from "react";

/** Animates a number from 0 (first time) or its last value up to `value`. */
export function useCountUp(value: number | null, duration = 900): number | null {
  const [shown, setShown] = useState(0);
  const fromRef = useRef(0);
  const first = useRef(true);

  useEffect(() => {
    if (value === null) {
      setShown(0);
      return;
    }
    const from = first.current ? 0 : fromRef.current;
    first.current = false;
    fromRef.current = value;
    if (from === value) {
      setShown(value);
      return;
    }
    let raf = 0;
    const start = Date.now();
    const tick = () => {
      const t = Math.min(1, (Date.now() - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setShown(from + (value - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return value === null ? null : shown;
}
