// Adapted from React Bits by David Haz. See LICENSE.md in this directory.
import { useRef, type CSSProperties, type PropsWithChildren } from "react";
import "./react-bits.css";

interface SpotlightCardProps extends PropsWithChildren {
  className?: string;
  spotlightColor?: string;
}

export function SpotlightCard({
  children,
  className = "",
  spotlightColor = "rgba(128, 170, 255, 0.13)",
}: SpotlightCardProps) {
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={ref}
      className={`card-spotlight ${className}`}
      style={{ "--spotlight-color": spotlightColor } as CSSProperties}
      onPointerMove={(event) => {
        if (event.pointerType === "touch" || !ref.current) return;
        const rect = ref.current.getBoundingClientRect();
        ref.current.style.setProperty("--mouse-x", `${event.clientX - rect.left}px`);
        ref.current.style.setProperty("--mouse-y", `${event.clientY - rect.top}px`);
      }}
    >
      {children}
    </div>
  );
}
