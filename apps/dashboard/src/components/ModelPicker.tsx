import { useEffect, useId, useMemo, useRef, useState } from "react";

export function ModelPicker({
  label,
  value,
  onChange,
  placeholder,
  suggestions,
  helperText,
  emptyState,
}: {
  label: string;
  value: string;
  onChange: (nextValue: string) => void;
  placeholder: string;
  suggestions: string[];
  helperText?: string;
  emptyState?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputId = useId();
  const uniqueSuggestions = useMemo(
    () => Array.from(new Set(suggestions.map((item) => item.trim()).filter(Boolean))),
    [suggestions],
  );

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  return (
    <label htmlFor={inputId}>
      {label}
      <div ref={rootRef} className="model-picker">
        <input
          id={inputId}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          placeholder={placeholder}
          autoComplete="off"
        />
        <button
          type="button"
          className="model-picker__toggle"
          aria-label={`Browse ${label.toLowerCase()} options`}
          onClick={() => setOpen((current) => !current)}
        >
          <span aria-hidden="true">▾</span>
        </button>
        {open ? (
          <div className="model-picker__menu">
            <button
              type="button"
              className={`model-picker__option${!value.trim() ? " model-picker__option--active" : ""}`}
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
            >
              Use provider default
            </button>
            {uniqueSuggestions.length ? (
              uniqueSuggestions.map((model) => (
                <button
                  key={model}
                  type="button"
                  className={`model-picker__option${value === model ? " model-picker__option--active" : ""}`}
                  onClick={() => {
                    onChange(model);
                    setOpen(false);
                  }}
                >
                  {model}
                </button>
              ))
            ) : (
              <div className="model-picker__empty">
                {emptyState ?? "No detected models yet. You can still type a custom model string."}
              </div>
            )}
          </div>
        ) : null}
      </div>
      {helperText ? <span className="section-footnote">{helperText}</span> : null}
    </label>
  );
}
