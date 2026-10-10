import { useId } from "react";

interface Option {
  value: string;
  label: string;
  count?: number;
}

export function SegmentedControl({
  label, value, options, onChange,
}: {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
}) {
  const name = useId();
  return (
    <fieldset className="segmented-control">
      <legend className="sr-only">{label}</legend>
      {options.map((option) => (
        <label key={option.value}>
          <input
            className="segmented-input"
            type="radio"
            name={name}
            value={option.value}
            aria-label={option.label}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
          />
          <span>
            {option.label}
            {option.count !== undefined && <small aria-hidden="true">{option.count}</small>}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
