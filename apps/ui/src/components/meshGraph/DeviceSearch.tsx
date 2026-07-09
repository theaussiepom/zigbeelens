import { useEffect, useMemo, useRef, useState } from "react";
import type { MeshEvidenceDevice, MeshEvidenceEdge } from "@/lib/meshEvidence";
import {
  DEVICE_SEARCH_HELPER,
  DEVICE_SEARCH_LABEL,
  DEVICE_SEARCH_PLACEHOLDER,
  deviceSearchNoResultsCopy,
} from "@/lib/meshGraphCopy";
import { searchDevices, type DeviceSearchResult } from "@/lib/meshGraphSearch";

function shortIeee(ieee: string): string {
  const bare = ieee.replace(/^0x/, "");
  return bare.length > 6 ? `…${bare.slice(-6)}` : ieee;
}

/**
 * Device search combobox for the graph toolbar.
 *
 * Frontend search over all devices the evidence model knows about (inventory,
 * latest snapshot, topology-only placeholders). Selecting a result hands the
 * device to the existing selected-device behaviour — it never moves nodes,
 * never recomputes layout and never touches saved connection choices.
 */
export function DeviceSearch({
  devices,
  edges,
  onSelectDevice,
}: {
  devices: MeshEvidenceDevice[];
  edges: MeshEvidenceEdge[];
  onSelectDevice: (device: MeshEvidenceDevice) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const results = useMemo(
    () => searchDevices(query, devices, edges),
    [query, devices, edges],
  );

  // Cmd+K / Ctrl+K focuses device search from anywhere on the page.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Close the result list when focus/clicks move outside the search control.
  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const select = (result: DeviceSearchResult) => {
    onSelectDevice(result.device);
    setQuery("");
    setOpen(false);
    setActiveIndex(0);
    inputRef.current?.focus();
  };

  const hasQuery = query.trim().length > 0;
  const showList = open && hasQuery;

  return (
    <div ref={containerRef} className="relative w-64 max-w-full">
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-label={DEVICE_SEARCH_LABEL}
        aria-expanded={showList}
        aria-controls="device-search-results"
        aria-activedescendant={
          showList && results[activeIndex]
            ? `device-search-option-${results[activeIndex].device.ieee_address}`
            : undefined
        }
        aria-autocomplete="list"
        title={DEVICE_SEARCH_HELPER}
        placeholder={DEVICE_SEARCH_PLACEHOLDER}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActiveIndex(0);
        }}
        onFocus={() => {
          if (hasQuery) setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            if (query) setQuery("");
            setOpen(false);
            return;
          }
          if (!showList) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActiveIndex((i) => Math.min(i + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActiveIndex((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const result = results[activeIndex];
            if (result) select(result);
          }
        }}
        className="w-full rounded-lg border border-zl-border bg-zl-surface-2 px-3 py-1.5 text-sm text-zl-text placeholder:text-zl-muted focus:border-zl-accent/60 focus:outline-none"
      />
      {query && (
        <button
          type="button"
          aria-label="Clear device search"
          onClick={() => {
            setQuery("");
            setOpen(false);
            inputRef.current?.focus();
          }}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-1 text-zl-muted hover:text-zl-text"
        >
          ×
        </button>
      )}
      {showList && (
        <div
          id="device-search-results"
          role="listbox"
          aria-label="Device search results"
          className="absolute left-0 right-0 top-full z-20 mt-1 max-h-80 overflow-y-auto rounded-lg border border-zl-border bg-zl-surface shadow-lg"
        >
          {results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-zl-muted">
              {deviceSearchNoResultsCopy(query.trim())}
            </p>
          ) : (
            results.map((result, index) => (
              <button
                key={result.device.ieee_address}
                id={`device-search-option-${result.device.ieee_address}`}
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => select(result)}
                className={`block w-full px-3 py-2 text-left text-sm ${
                  index === activeIndex ? "bg-zl-accent/15" : "hover:bg-zl-surface-2"
                }`}
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-medium text-zl-text">
                    {result.device.friendly_name}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-zl-muted">
                    {shortIeee(result.device.ieee_address)}
                  </span>
                </span>
                {(result.device.manufacturer || result.device.model) && (
                  <span className="mt-0.5 block truncate text-[11px] text-zl-muted">
                    {[result.device.manufacturer, result.device.model]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                )}
                {result.badges.length > 0 && (
                  <span className="mt-1 flex flex-wrap gap-1">
                    {result.badges.map((badge) => (
                      <span
                        key={badge}
                        className="rounded-full border border-zl-border bg-zl-surface-2 px-1.5 py-0.5 text-[10px] text-zl-muted"
                      >
                        {badge}
                      </span>
                    ))}
                  </span>
                )}
                {result.limitedTopologyNote && (
                  <span className="mt-1 block text-[11px] leading-snug text-zl-muted">
                    {result.limitedTopologyNote}
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
