import { forwardRef, InputHTMLAttributes } from "react";

const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput(props, ref) {
  return <input ref={ref} {...props} />;
});

export default TextInput;
