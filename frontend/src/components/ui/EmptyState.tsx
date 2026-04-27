import { ReactNode } from "react";
import Card from "./Card";

export default function EmptyState({
  title,
  description,
  action,
  className = "",
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`emptyState${className ? ` ${className}` : ""}`}>
      <div className="emptyStateTitle">{title}</div>
      {description ? <div className="emptyStateDescription">{description}</div> : null}
      {action ? <div className="emptyStateAction">{action}</div> : null}
    </Card>
  );
}
