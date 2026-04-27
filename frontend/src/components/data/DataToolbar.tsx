import { CSSProperties, ReactNode } from "react";

type DataToolbarProps = {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  compact?: boolean;
  style?: CSSProperties;
};

export default function DataToolbar({
  title,
  subtitle,
  actions,
  children,
  className = "",
  compact = false,
  style,
}: DataToolbarProps) {
  return (
    <div className={`dataToolbar${compact ? " isCompact" : ""}${className ? ` ${className}` : ""}`} style={style}>
      {(title || subtitle) ? (
        <div className="dataToolbarMain">
          {title ? <div className="dataToolbarTitle">{title}</div> : null}
          {subtitle ? <div className="dataToolbarSubtitle">{subtitle}</div> : null}
        </div>
      ) : null}
      {children ? <div className="dataToolbarContent">{children}</div> : null}
      {actions ? <div className="dataToolbarActions">{actions}</div> : null}
    </div>
  );
}
