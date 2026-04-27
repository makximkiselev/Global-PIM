import { ReactNode } from "react";

type AlertTone = "error" | "success" | "info";

type AlertProps = {
  children: ReactNode;
  tone?: AlertTone;
  className?: string;
};

export default function Alert({ children, tone = "info", className = "" }: AlertProps) {
  const toneClass =
    tone === "error" ? "uiAlertError" : tone === "success" ? "uiAlertSuccess" : "uiAlertInfo";
  return <div className={`uiAlert ${toneClass}${className ? ` ${className}` : ""}`}>{children}</div>;
}
