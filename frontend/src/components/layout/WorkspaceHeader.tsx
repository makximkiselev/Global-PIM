import type { ReactNode } from "react";

type WorkspaceHeaderTab = {
  key: string;
  label: string;
  hint?: string;
};

type WorkspaceHeaderBadge = {
  label: string;
  tone?: "neutral" | "active" | "warning" | "danger";
};

type WorkspaceHeaderProps = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  context?: string;
  badges?: WorkspaceHeaderBadge[];
  tabs?: WorkspaceHeaderTab[];
  activeTab?: string;
  onTabChange?: (key: string) => void;
  actions?: ReactNode;
  className?: string;
};

export default function WorkspaceHeader({
  eyebrow,
  title,
  subtitle,
  context,
  badges = [],
  tabs = [],
  activeTab,
  onTabChange,
  actions,
  className = "",
}: WorkspaceHeaderProps) {
  return (
    <section className={`workspaceHeader${className ? ` ${className}` : ""}`}>
      <div className="workspaceHeaderMain">
        {eyebrow ? <div className="workspaceHeaderEyebrow">{eyebrow}</div> : null}
        <div className="workspaceHeaderTitleRow">
          <h1>{title}</h1>
          {context ? <span className="workspaceHeaderContext">{context}</span> : null}
          {badges.map((badge) => (
            <span
              key={`${badge.label}-${badge.tone || "neutral"}`}
              className={`workspaceHeaderBadge is-${badge.tone || "neutral"}`}
            >
              {badge.label}
            </span>
          ))}
        </div>
        {subtitle ? <p className="workspaceHeaderSubtitle">{subtitle}</p> : null}
      </div>

      {tabs.length ? (
        <div className="workspaceHeaderTabs" aria-label="Разделы рабочего экрана">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`workspaceHeaderTab${tab.key === activeTab ? " isActive" : ""}`}
              onClick={() => onTabChange?.(tab.key)}
            >
              <strong>{tab.label}</strong>
              {tab.hint ? <span>{tab.hint}</span> : null}
            </button>
          ))}
        </div>
      ) : null}

      {actions ? <div className="workspaceHeaderActions">{actions}</div> : null}
    </section>
  );
}
