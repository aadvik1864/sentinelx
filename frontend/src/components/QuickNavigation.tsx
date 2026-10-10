import { useRef, useState } from "react";
import { ArrowUpRight, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Modal } from "./ui";
import type { NavigationItem } from "../utils/navigation";

export function QuickNavigation({ items, onClose }: { items: NavigationItem[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const list = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const matches = items.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase()));

  function open(path: string) {
    onClose();
    navigate(path);
  }

  return (
    <Modal title="Go to a page" onClose={onClose} initialFocus="[data-quick-search]">
      <form className="quick-navigation" onSubmit={(event) => {
        event.preventDefault();
        if (matches[0]) open(matches[0].path);
      }}>
        <label className="quick-navigation-search">
          <Search size={18} />
          <span className="sr-only">Find a page</span>
          <input
            data-quick-search
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Try alerts, activity, or settings"
            autoComplete="off"
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" && matches.length) {
                event.preventDefault();
                list.current?.querySelector<HTMLButtonElement>("button")?.focus();
              }
            }}
          />
        </label>
        <div className="quick-navigation-results" ref={list} onKeyDown={(event) => {
          if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
          const buttons = Array.from(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
          const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
          if (current < 0) return;
          event.preventDefault();
          buttons[(current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
        }}>
          {matches.map((item) => (
            <button type="button" key={item.path} onClick={() => open(item.path)}>
              <item.icon size={19} /><span>{item.label}</span><ArrowUpRight size={16} />
            </button>
          ))}
          {!matches.length && <p className="quick-navigation-empty">No matching pages. Try a different name.</p>}
        </div>
        <p className="quick-navigation-hint">Use the arrow keys to choose a page, Enter to open it, or Escape to close.</p>
      </form>
    </Modal>
  );
}
