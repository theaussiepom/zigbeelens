/** Connection-type checkbox. Helper copy renders only when provided. */
export function ConnectionCheckbox({
  label,
  helper,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  helper?: string;
  checked: boolean;
  onChange?: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={`block ${disabled ? "cursor-not-allowed" : "cursor-pointer"}`}>
      <span className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.checked)}
          className="h-4 w-4 accent-[#5b9fd4]"
        />
        <span className={`text-sm ${disabled && !checked ? "text-zl-muted/60" : "text-zl-text"}`}>
          {label}
        </span>
      </span>
      {helper && (
        <span className="mt-0.5 block pl-6 text-[11px] leading-snug text-zl-muted">{helper}</span>
      )}
    </label>
  );
}
