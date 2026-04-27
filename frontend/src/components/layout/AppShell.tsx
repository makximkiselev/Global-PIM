import { ReactNode } from "react";

export default function AppShell({
  sidebar,
  topbar,
  eyebrow,
  title,
  showHeading = true,
  children,
}: {
  sidebar: ReactNode;
  topbar?: ReactNode;
  eyebrow: string;
  title: string;
  showHeading?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="shell shellSidebarLayout">
      {sidebar}
      <main className="shellContent">
        {topbar ? <div className="shellWorkspaceTopbar">{topbar}</div> : null}
        {showHeading ? (
          <div className="shellContentTop">
            <div className="shellContentEyebrow">{eyebrow}</div>
            <div className="shellContentTitle">{title}</div>
          </div>
        ) : null}
        <div className="shellContentBody">{children}</div>
      </main>
    </div>
  );
}
