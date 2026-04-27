import { ReactNode } from "react";

export default function DataFilters({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`dataFilters${className ? ` ${className}` : ""}`}>{children}</div>;
}
