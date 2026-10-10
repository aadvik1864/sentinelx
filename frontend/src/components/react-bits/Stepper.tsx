/**
 * Adapted from React Bits Stepper by David Haz (MIT + Commons Clause).
 * https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Components/Stepper/Stepper.tsx
 * Local changes: controlled steps, validation gates, keyboard buttons, scoped styles,
 * natural content height, and reduced-motion support. See LICENSE.md in this directory.
 */
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Children, useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";

interface StepperProps {
  labels: string[];
  step: number;
  onStepChange: (step: number) => void;
  onNext: () => void;
  nextLabel?: string;
  busy?: boolean;
  nextDisabled?: boolean;
  children: ReactNode;
}

function StepContent({ children, id }: { children: ReactNode; id: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <div className="setup-step-content" ref={ref} tabIndex={-1} id={id}>
      {children}
    </div>
  );
}

export function Stepper({
  labels,
  step,
  onStepChange,
  onNext,
  nextLabel,
  busy = false,
  nextDisabled = false,
  children,
}: StepperProps) {
  const reduced = useReducedMotion();
  const id = useId();
  const pages = Children.toArray(children);
  return (
    <div className="rb-stepper" data-motion={reduced ? "static" : "animated"}>
      <ol className="setup-progress" aria-label="Setup progress">
        {labels.map((label, index) => (
          <li
            key={label}
            className={step === index + 1 ? "current" : step > index + 1 ? "complete" : ""}
            aria-current={step === index + 1 ? "step" : undefined}
          >
            <button
              type="button"
              disabled={busy || index + 1 >= step}
              onClick={() => onStepChange(index + 1)}
              aria-label={`Step ${index + 1}: ${label}`}
            >
              <span className="setup-step-number" aria-hidden="true">
                {step > index + 1 ? <Check size={15} /> : index + 1}
              </span>
              <span>{label}</span>
            </button>
          </li>
        ))}
      </ol>
      <p className="setup-step-count" aria-live="polite">
        Step {step} of {pages.length} · {labels[step - 1]}
      </p>
      <AnimatePresence initial={false} mode="wait">
        <motion.div
          key={step}
          initial={reduced ? false : { opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: reduced ? 1 : 0, x: reduced ? 0 : -8 }}
          transition={{ duration: reduced ? 0 : 0.16 }}
        >
          <StepContent id={`${id}-step`}>{pages[step - 1]}</StepContent>
        </motion.div>
      </AnimatePresence>
      <div className="setup-footer">
        {step > 1 ? (
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => onStepChange(step - 1)}
          >
            <ChevronLeft size={16} />Back
          </button>
        ) : <span />}
        <button
          type="button"
          className="button primary"
          disabled={busy || nextDisabled}
          onClick={onNext}
        >
          {busy ? "Saving…" : nextLabel ?? "Continue"}
          {!busy && <ChevronRight size={16} />}
        </button>
      </div>
    </div>
  );
}

export function Step({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <section className="setup-step">
      <h3>{title}</h3>
      {description && <p className="setup-step-description">{description}</p>}
      {children}
    </section>
  );
}
