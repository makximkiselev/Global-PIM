import { ReactNode } from "react";

export default function StatusRow({
  label,
  value,
  meta,
  className = "",
}: {
  label: ReactNode;
  value: ReactNode;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`statusRow${className ? ` ${className}` : ""}`}>
      <div className="statusRowLabel">{label}</div>
      <div className="statusRowMain">
        <div className="statusRowValue">{value}</div>
        {meta ? <div className="statusRowMeta">{meta}</div> : null}
      </div>
    </div>
  );
}
