import { ReactNode } from "react";
import Card from "../ui/Card";

type InspectorPanelProps = {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export default function InspectorPanel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: InspectorPanelProps) {
  return (
    <Card
      className={`inspectorPanel${className ? ` ${className}` : ""}`}
      actions={actions}
      title={title}
    >
      {subtitle ? <div className="inspectorPanelSubtitle">{subtitle}</div> : null}
      <div className="inspectorPanelBody">{children}</div>
    </Card>
  );
}
