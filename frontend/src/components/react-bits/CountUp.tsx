// Adapted from React Bits by David Haz. See LICENSE.md in this directory.
import { animate, useMotionValue } from "motion/react";
import { useEffect, useMemo, useRef } from "react";
import { useReducedMotion } from "../../hooks/useReducedMotion";

interface CountUpProps {
  to: number;
  duration?: number;
  decimals?: number;
  className?: string;
}

export function CountUp({
  to,
  duration = 0.85,
  decimals = 0,
  className = "",
}: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const value = useMotionValue(0);
  const reducedMotion = useReducedMotion();
  const formatter = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }),
    [decimals],
  );

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (reducedMotion || duration <= 0) {
      value.jump(to);
      element.textContent = formatter.format(to);
      element.dataset.counting = "false";
      return;
    }

    element.dataset.counting = "true";
    const controls = animate(value, to, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (latest) => {
        element.textContent = formatter.format(latest);
      },
      onComplete: () => {
        // Always settle on the authoritative server value, not a spring approximation.
        element.textContent = formatter.format(to);
        element.dataset.counting = "false";
      },
    });
    return () => {
      controls.stop();
      element.dataset.counting = "false";
    };
  }, [to, duration, formatter, reducedMotion, value]);

  return (
    <span className={`count-up ${className}`}>
      {/* Assistive technology gets the real value, never intermediate counts. */}
      <span className="sr-only">{formatter.format(to)}</span>
      <span ref={ref} aria-hidden="true">
        {formatter.format(to)}
      </span>
    </span>
  );
}
