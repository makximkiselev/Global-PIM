import type { ReactNode } from "react";
import "../styles/catalog-sidebar.css";

type SidebarAction = {
  label: string;
  onClick: () => void;
  kind?: "primary" | "default";
  disabled?: boolean;
};

type Props = {
  title: string;
  hint?: string;
  primaryAction?: SidebarAction | null;
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  controls?: ReactNode;
  children: ReactNode;
  className?: string;
};

export default function CategorySidebar({
  title,
  hint,
  primaryAction,
  searchValue,
  onSearchChange,
  searchPlaceholder = "Быстрый поиск",
  controls,
  children,
  className = "",
}: Props) {
  return (
    <aside className={`csb-shell ${className}`.trim()}>
      <div className="csb-head">
        <div className="csb-titleBlock">
          <div className="csb-title">{title}</div>
          {hint ? <div className="csb-hint">{hint}</div> : null}
        </div>
        {primaryAction ? (
          <button
            className={`btn ${primaryAction.kind === "primary" ? "primary" : ""} sm`}
            type="button"
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
          >
            {primaryAction.label}
          </button>
        ) : null}
      </div>

      <div className="csb-toolbar">
        <div className="csb-search">
          <span aria-hidden="true">🔎</span>
          <input
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
          />
        </div>
        {controls ? <div className="csb-controls">{controls}</div> : null}
      </div>

      <div className="csb-body">{children}</div>
    </aside>
  );
}
