import { ButtonHTMLAttributes, ReactNode } from "react";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  tone?: "default" | "danger";
};

export default function IconButton({
  children,
  className = "",
  tone = "default",
  type = "button",
  ...props
}: IconButtonProps) {
  const toneClass = tone === "danger" ? " danger" : "";
  return (
    <button type={type} className={`icon-btn${toneClass}${className ? ` ${className}` : ""}`} {...props}>
      {children}
    </button>
  );
}
