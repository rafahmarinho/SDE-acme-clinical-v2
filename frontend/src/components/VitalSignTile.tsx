interface Props {
  label: string;
  value: number | string | null | undefined;
  unit?: string;
  low?: number;
  high?: number;
  degraded?: boolean;
}

/** Large-number vital sign display; out-of-range values are flagged with text, not only color. */
export function VitalSignTile({ label, value, unit, low, high, degraded }: Props) {
  const numeric = typeof value === "number" ? value : null;
  const outOfRange =
    numeric !== null && ((low !== undefined && numeric < low) || (high !== undefined && numeric > high));
  const display = value === null || value === undefined || value === "" ? "--" : String(value);
  const cls = ["vital", outOfRange ? "vital-alert" : "", degraded ? "vital-degraded" : ""].join(" ");
  return (
    <div className={cls}>
      <div className="vital-label">{label}</div>
      <div className="vital-value" aria-live="polite">
        {display}
        {unit && <span className="vital-unit"> {unit}</span>}
      </div>
      {low !== undefined && high !== undefined && (
        <div className="vital-range">
          Limits {low}–{high}
        </div>
      )}
      {outOfRange && <div className="vital-flag">Out of range</div>}
      {degraded && <div className="vital-flag">Signal quality degraded</div>}
    </div>
  );
}
