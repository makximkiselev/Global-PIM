import { SelectHTMLAttributes } from "react";

export default function Select({ className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`uiSelect${className ? ` ${className}` : ""}`} {...props} />;
}
