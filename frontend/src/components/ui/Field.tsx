import { ReactNode } from "react";

type FieldProps = {
  label: string;
  children: ReactNode;
  error?: string;
  hint?: string;
  className?: string;
};

export default function Field({ label, children, error, hint, className = "" }: FieldProps) {
  return (
    <label className={`authField${className ? ` ${className}` : ""}`}>
      <span>{label}</span>
      {children}
      {hint ? <div className="uiFieldHint">{hint}</div> : null}
      {error ? <div className="authError">{error}</div> : null}
    </label>
  );
}
