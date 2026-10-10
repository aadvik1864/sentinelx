// Square-grid variant adapted from React Bits by David Haz. See LICENSE.md.
import { useEffect, useRef } from "react";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import "./react-bits.css";

interface ShapeGridProps {
  speed?: number;
  squareSize?: number;
  borderColor?: string;
  hoverFillColor?: string;
  paused?: boolean;
}

export function ShapeGrid({
  speed = 7,
  squareSize = 48,
  borderColor = "rgba(128, 170, 255, 0.12)",
  hoverFillColor = "rgba(107, 202, 185, 0.10)",
  paused = false,
}: ShapeGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const offsetRef = useRef(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    // Keep the CSS grid fallback on older browsers and non-canvas environments.
    if (!canvas || !container || typeof ResizeObserver === "undefined") return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    container.dataset.rendered = "true";
    let width = 0;
    let height = 0;
    let offset = offsetRef.current;
    let frame = 0;
    let lastTime = 0;
    let visible = true;
    let pointer: { x: number; y: number } | null = null;
    const cellSize = Math.max(24, squareSize);

    const drawGrid = () => {
      ctx.clearRect(0, 0, width, height);
      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 0.7;
      const hoveredX = pointer ? Math.floor((pointer.x - offset) / cellSize) : null;
      const hoveredY = pointer ? Math.floor((pointer.y - offset) / cellSize) : null;
      const columns = Math.ceil(width / cellSize) + 1;
      const rows = Math.ceil(height / cellSize) + 1;
      for (let col = -1; col < columns; col++) {
        for (let row = -1; row < rows; row++) {
          const x = col * cellSize + offset;
          const y = row * cellSize + offset;
          if (col === hoveredX && row === hoveredY) {
            ctx.fillStyle = hoverFillColor;
            ctx.fillRect(x, y, cellSize, cellSize);
          }
          ctx.strokeRect(x, y, cellSize, cellSize);
        }
      }
    };

    const shouldAnimate = () =>
      !paused && !reducedMotion && visible && !document.hidden && width > 0 && height > 0;

    const updateAnimation = (time: number) => {
      frame = 0;
      if (!shouldAnimate()) return;
      const elapsed = lastTime ? time - lastTime : 0;
      // Decorative background only: cap work at 30 fps and avoid jumps on resume.
      if (!lastTime || elapsed >= 1000 / 30) {
        offset = (offset + Math.min(elapsed, 50) / 1000 * Math.max(0, speed)) % cellSize;
        drawGrid();
        lastTime = time;
      }
      frame = requestAnimationFrame(updateAnimation);
    };

    const syncAnimation = () => {
      if (!shouldAnimate()) {
        cancelAnimationFrame(frame);
        frame = 0;
        lastTime = 0;
      } else if (!frame) {
        frame = requestAnimationFrame(updateAnimation);
      }
    };

    const resizeCanvas = () => {
      ({ width, height } = container.getBoundingClientRect());
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawGrid();
      syncAnimation();
    };

    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      const rect = container.getBoundingClientRect();
      pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      if (!shouldAnimate()) drawGrid();
    };
    const onPointerLeave = () => {
      pointer = null;
      if (!shouldAnimate()) drawGrid();
    };

    const resizeObserver = new ResizeObserver(resizeCanvas);
    resizeObserver.observe(container);
    const intersectionObserver = typeof IntersectionObserver !== "undefined"
      ? new IntersectionObserver(([entry]) => {
          visible = entry.isIntersecting;
          syncAnimation();
        })
      : null;
    intersectionObserver?.observe(container);
    document.addEventListener("visibilitychange", syncAnimation);
    // Listen on the story panel so text above the decorative canvas stays interactive.
    const panel = container.parentElement;
    panel?.addEventListener("pointermove", onPointerMove);
    panel?.addEventListener("pointerleave", onPointerLeave);
    resizeCanvas();

    return () => {
      offsetRef.current = offset;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      intersectionObserver?.disconnect();
      document.removeEventListener("visibilitychange", syncAnimation);
      panel?.removeEventListener("pointermove", onPointerMove);
      panel?.removeEventListener("pointerleave", onPointerLeave);
      delete container.dataset.rendered;
    };
  }, [speed, squareSize, borderColor, hoverFillColor, paused, reducedMotion]);

  return (
    <div
      ref={containerRef}
      className="shape-grid"
      aria-hidden="true"
      data-motion={paused || reducedMotion ? "static" : "animated"}
    >
      <canvas ref={canvasRef} className="shape-grid-canvas" />
    </div>
  );
}
