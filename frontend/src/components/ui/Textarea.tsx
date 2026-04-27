import { forwardRef, TextareaHTMLAttributes } from "react";

const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className = "", ...props },
  ref,
) {
  return <textarea ref={ref} className={`uiTextarea${className ? ` ${className}` : ""}`} {...props} />;
});

export default Textarea;
