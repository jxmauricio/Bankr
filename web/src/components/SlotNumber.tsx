import { useEffect, useRef, useState } from "react";

const DIGIT_STAGGER_MS = 35;
const SPIN_DURATION_MS = 550;
const TICK_MS = 45;

function randomDigit(): string {
  return Math.floor(Math.random() * 10).toString();
}

/**
 * Renders a formatted number string (e.g. from formatMoney) with a
 * slot-machine reveal: each digit rolls through random values and locks in
 * left-to-right, cascading like reels stopping. Non-digit characters ($, ,
 * . -) render immediately. Re-plays whenever `value` changes, so it also
 * animates on period/data changes, not just first mount. Relies on the
 * caller using a tabular/monospace font (already the app convention for
 * money) so digits don't jitter in width while spinning.
 */
export function SlotNumber({ value, className }: { value: string; className?: string }) {
  const [display, setDisplay] = useState(() => value.replace(/[0-9]/g, () => randomDigit()));
  const startRef = useRef(0);

  useEffect(() => {
    startRef.current = performance.now();
    const id = setInterval(() => {
      const elapsed = performance.now() - startRef.current;
      let allSettled = true;
      let digitIndex = 0;
      const next = value
        .split("")
        .map((ch) => {
          if (!/[0-9]/.test(ch)) return ch;
          const settleAt = digitIndex * DIGIT_STAGGER_MS + SPIN_DURATION_MS;
          digitIndex += 1;
          if (elapsed >= settleAt) return ch;
          allSettled = false;
          return randomDigit();
        })
        .join("");
      setDisplay(next);
      if (allSettled) clearInterval(id);
    }, TICK_MS);
    return () => clearInterval(id);
  }, [value]);

  return <span className={className}>{display}</span>;
}
