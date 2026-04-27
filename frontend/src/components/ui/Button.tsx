import { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "default" | "primary" | "danger";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: ButtonVariant;
};

export default function Button({ children, className = "", variant = "default", type = "button", ...props }: ButtonProps) {
  const variantClass = variant === "default" ? "" : ` ${variant}`;
  return (
    <button type={type} className={`btn${variantClass}${className ? ` ${className}` : ""}`} {...props}>
      {children}
    </button>
  );
}
