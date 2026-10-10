import { act, fireEvent, render, screen } from "@testing-library/react";
import { animate } from "motion/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CountUp } from "../components/react-bits/CountUp";
import { ShapeGrid } from "../components/react-bits/ShapeGrid";
import { SpotlightCard } from "../components/react-bits/SpotlightCard";

vi.mock("motion/react", async (importOriginal) => {
  const original = await importOriginal<typeof import("motion/react")>();
  return { ...original, animate: vi.fn(() => ({ stop: vi.fn() })) };
});

let media: {
  matches: boolean;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
};
let listeners: Set<() => void>;

beforeEach(() => {
  vi.clearAllMocks();
  listeners = new Set();
  media = {
    matches: false,
    addEventListener: vi.fn((_event, listener: () => void) => listeners.add(listener)),
    removeEventListener: vi.fn((_event, listener: () => void) => listeners.delete(listener)),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => media));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("CountUp", () => {
  it("keeps the authoritative number accessible while the visible count animates", () => {
    const { container } = render(<CountUp to={1250} />);
    expect(container.querySelector(".sr-only")).toHaveTextContent("1,250");
    const visual = container.querySelector('[aria-hidden="true"]');
    expect(visual).toHaveAttribute("data-counting", "true");
    const options = (vi.mocked(animate).mock.calls[0] as unknown[])[2] as {
      onUpdate: (value: number) => void;
      onComplete: () => void;
    };
    act(() => options.onUpdate(125));
    expect(visual).toHaveTextContent("125");
    expect(container.querySelector(".sr-only")).toHaveTextContent("1,250");
    act(options.onComplete);
    expect(visual).toHaveTextContent("1,250");
    expect(visual).toHaveAttribute("data-counting", "false");
  });

  it("renders the final value immediately for reduced motion, including updates", () => {
    media.matches = true;
    const { container, rerender } = render(<CountUp to={14} />);
    expect(animate).not.toHaveBeenCalled();
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("14");
    rerender(<CountUp to={28} />);
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("28");
    expect(container.querySelector(".sr-only")).toHaveTextContent("28");
  });

  it("stops an animation when reduced motion is enabled at runtime", () => {
    const { container } = render(<CountUp to={72} />);
    const controls = vi.mocked(animate).mock.results[0].value;
    act(() => {
      media.matches = true;
      listeners.forEach((listener) => listener());
    });
    expect(controls.stop).toHaveBeenCalled();
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("72");
    expect(container.querySelector('[aria-hidden="true"]')).toHaveAttribute("data-counting", "false");
  });

  it("stops the previous transition when the server value changes and on unmount", () => {
    const { rerender, unmount } = render(<CountUp to={10} />);
    const previous = vi.mocked(animate).mock.results[0].value;
    rerender(<CountUp to={11} />);
    expect(previous.stop).toHaveBeenCalled();
    const current = vi.mocked(animate).mock.results[1].value;
    unmount();
    expect(current.stop).toHaveBeenCalled();
  });
});

describe("SpotlightCard", () => {
  it("tracks pointer position without adding a keyboard stop to a static card", () => {
    const { container } = render(<SpotlightCard><button>Review evidence</button></SpotlightCard>);
    const card = container.firstElementChild as HTMLDivElement;
    vi.spyOn(card, "getBoundingClientRect").mockReturnValue({ left: 10, top: 20 } as DOMRect);
    fireEvent(card, new MouseEvent("pointermove", { bubbles: true, clientX: 80, clientY: 60 }));
    expect(card.style.getPropertyValue("--mouse-x")).toBe("70px");
    expect(card.style.getPropertyValue("--mouse-y")).toBe("40px");
    expect(card).not.toHaveAttribute("tabindex");
    expect(screen.getByRole("button", { name: "Review evidence" })).toBeVisible();
  });

  it("ignores touch gestures so scrolling does not move the spotlight", () => {
    const { container } = render(<SpotlightCard>Events</SpotlightCard>);
    const card = container.firstElementChild as HTMLDivElement;
    const event = new MouseEvent("pointermove", { bubbles: true, clientX: 80 });
    Object.defineProperty(event, "pointerType", { value: "touch" });
    fireEvent(card, event);
    expect(card.style.getPropertyValue("--mouse-x")).toBe("");
  });
});

function mockCanvas() {
  const context = {
    clearRect: vi.fn(), strokeRect: vi.fn(), fillRect: vi.fn(), setTransform: vi.fn(),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 400, height: 300, left: 0, top: 0 } as DOMRect);
  const raf = vi.fn(() => 1);
  const cancel = vi.fn();
  vi.stubGlobal("requestAnimationFrame", raf);
  vi.stubGlobal("cancelAnimationFrame", cancel);
  const disconnect = vi.fn();
  vi.stubGlobal("ResizeObserver", class {
    observe = vi.fn();
    disconnect = disconnect;
  });
  let onIntersection: IntersectionObserverCallback;
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: IntersectionObserverCallback) { onIntersection = callback; }
    observe = vi.fn();
    disconnect = disconnect;
  });
  let hidden = false;
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  return {
    context, raf, cancel, disconnect,
    setVisible(visible: boolean) {
      onIntersection([{ isIntersecting: visible } as IntersectionObserverEntry], {} as IntersectionObserver);
    },
    setHidden(value: boolean) {
      hidden = value;
      fireEvent(document, new Event("visibilitychange"));
    },
  };
}

describe("ShapeGrid", () => {
  it("draws a static grid and schedules no frames for reduced motion", () => {
    media.matches = true;
    const { context, raf } = mockCanvas();
    render(<ShapeGrid />);
    expect(context.strokeRect).toHaveBeenCalled();
    expect(raf).not.toHaveBeenCalled();
  });

  it("supports a manual pause and cleans up observers and animation frames", () => {
    const { raf, cancel, disconnect } = mockCanvas();
    const { rerender, unmount } = render(<ShapeGrid paused />);
    expect(raf).not.toHaveBeenCalled();
    rerender(<ShapeGrid paused={false} />);
    expect(raf).toHaveBeenCalledOnce();
    unmount();
    expect(cancel).toHaveBeenCalledWith(1);
    expect(disconnect).toHaveBeenCalled();
  });

  it("suspends rendering offscreen or in a hidden tab and resumes when visible", () => {
    const canvas = mockCanvas();
    render(<ShapeGrid />);
    expect(canvas.raf).toHaveBeenCalledOnce();
    canvas.setVisible(false);
    expect(canvas.cancel).toHaveBeenCalledWith(1);
    canvas.setVisible(true);
    expect(canvas.raf).toHaveBeenCalledTimes(2);
    canvas.setHidden(true);
    expect(canvas.cancel).toHaveBeenCalledTimes(2);
    canvas.setHidden(false);
    expect(canvas.raf).toHaveBeenCalledTimes(3);
  });

  it("uses the static CSS fallback when canvas sizing is unavailable", () => {
    vi.stubGlobal("ResizeObserver", undefined);
    const { container } = render(<ShapeGrid />);
    expect(container.querySelector(".shape-grid")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector(".shape-grid")).not.toHaveAttribute("data-rendered");
  });
});
