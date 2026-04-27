import { MouseEvent, ReactNode } from "react";
import { flushSync } from "react-dom";
import { Link, useNavigate } from "react-router-dom";

declare global {
  interface Document {
    startViewTransition?: (update: () => void | Promise<void>) => {
      finished: Promise<void>;
      ready: Promise<void>;
      updateCallbackDone: Promise<void>;
      skipTransition: () => void;
    };
  }
}

type AuthViewTransitionLinkProps = {
  to: string;
  className?: string;
  children: ReactNode;
};

export default function AuthViewTransitionLink({
  to,
  className,
  children,
}: AuthViewTransitionLinkProps) {
  const navigate = useNavigate();

  function onClick(event: MouseEvent<HTMLAnchorElement>) {
    const startTransition = document.startViewTransition?.bind(document);
    if (!startTransition) {
      return;
    }

    event.preventDefault();
    startTransition(() => {
      flushSync(() => {
        navigate(to);
      });
    });
  }

  return (
    <Link to={to} className={className} onClick={onClick}>
      {children}
    </Link>
  );
}
