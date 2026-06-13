import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";

type WorkspaceEmptyAction = {
  label: string;
  href?: string;
  onClick?: () => void;
  primary?: boolean;
};

type WorkspaceEmptyStateProps = {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: WorkspaceEmptyAction[];
  children?: ReactNode;
  className?: string;
};

export default function WorkspaceEmptyState({
  eyebrow = "Рабочая область",
  title,
  description,
  actions = [],
  children,
  className = "",
}: WorkspaceEmptyStateProps) {
  const orgPath = useOrgPath();

  return (
    <section className={`workspaceEmptyState${className ? ` ${className}` : ""}`}>
      <div className="workspaceEmptyStateMain">
        <div className="workspaceEmptyStateEyebrow">{eyebrow}</div>
        <h2>{title}</h2>
        <p>{description}</p>
        {actions.length ? (
          <div className="workspaceEmptyStateActions">
            {actions.map((action) => {
              const className = `btn${action.primary ? " primary" : ""}`;
              if (action.href) {
                return (
                  <Link key={action.label} className={className} to={orgPath(action.href)}>
                    {action.label}
                  </Link>
                );
              }
              return (
                <button key={action.label} className={className} type="button" onClick={action.onClick}>
                  {action.label}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
      {children ? <div className="workspaceEmptyStateAside">{children}</div> : null}
    </section>
  );
}
