// The only password input in the app: masked by default; "Show" is an explicit action and re-masks
// when the field loses focus or the form is submitted (parent remounts/clears the value).
import { useId, useState } from "react";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  minLength?: number;
  maxLength?: number;
  required?: boolean;
  describedBy?: string;
}

export function PasswordField({ label, value, onChange, autoComplete, minLength, maxLength = 128, required = true, describedBy }: Props) {
  const [visible, setVisible] = useState(false);
  const id = useId();
  return (
    <div className="field password-field">
      <label htmlFor={id}>{label}</label>
      <div className="row">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          required={required}
          minLength={minLength}
          maxLength={maxLength}
          aria-describedby={describedBy}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={() => setVisible(false)}
        />
        <button
          type="button"
          className="secondary"
          aria-pressed={visible}
          aria-controls={id}
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          onMouseDown={(e) => e.preventDefault()} // keep focus in the input so blur does not re-mask first
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? "Hide" : "Show"}
        </button>
      </div>
    </div>
  );
}
