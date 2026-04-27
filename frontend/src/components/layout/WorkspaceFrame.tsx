import type { ReactNode } from "react";

type WorkspaceFrameProps = {
  sidebar?: ReactNode;
  main: ReactNode;
  inspector?: ReactNode;
  className?: string;
};

export default function WorkspaceFrame({
  sidebar,
  main,
  inspector,
  className = "",
}: WorkspaceFrameProps) {
  const mode = sidebar && inspector ? "workspaceFrameThree" : inspector ? "workspaceFrameTwo" : "workspaceFrameSingle";

  return (
    <div className={`workspaceFrame ${mode}${className ? ` ${className}` : ""}`}>
      {sidebar ? <aside className="workspaceFrameSidebar">{sidebar}</aside> : null}
      <section className="workspaceFrameMain">{main}</section>
      {inspector ? <aside className="workspaceFrameInspector">{inspector}</aside> : null}
    </div>
  );
}
