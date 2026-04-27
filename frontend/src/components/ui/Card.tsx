import { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";

type CardProps<T extends ElementType = "div"> = {
  children: ReactNode;
  title?: string;
  actions?: ReactNode;
  as?: T;
} & Omit<ComponentPropsWithoutRef<T>, "children">;

export default function Card<T extends ElementType = "div">({
  children,
  title,
  actions,
  className = "",
  as,
  ...props
}: CardProps<T>) {
  const Component = as || "div";
  return (
    <Component className={`card${className ? ` ${className}` : ""}`} {...props}>
      {title || actions ? (
        <div className="card-head">
          {title ? <div className="card-title">{title}</div> : <div />}
          {actions}
        </div>
      ) : null}
      {children}
    </Component>
  );
}
