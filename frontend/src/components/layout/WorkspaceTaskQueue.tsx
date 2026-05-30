import type { ReactNode } from "react";
import { Link } from "react-router-dom";

type WorkspaceTaskItem = {
  key: string;
  label: string;
  description: string;
  status?: "todo" | "active" | "done" | "blocked";
  href?: string;
  actionLabel?: string;
  meta?: string;
};

type WorkspaceTaskQueueProps = {
  title?: string;
  items: WorkspaceTaskItem[];
  aside?: ReactNode;
  className?: string;
};

const STATUS_LABEL: Record<NonNullable<WorkspaceTaskItem["status"]>, string> = {
  todo: "Дальше",
  active: "Сейчас",
  done: "Готово",
  blocked: "Блокер",
};

export default function WorkspaceTaskQueue({
  title = "Следующие действия",
  items,
  aside,
  className = "",
}: WorkspaceTaskQueueProps) {
  if (!items.length) return null;
  const activeItem = items.find((item) => item.status === "active" || item.status === "blocked") || items[0];

  return (
    <section className={`workspaceTaskQueue${className ? ` ${className}` : ""}`} aria-label={title}>
      <div className="workspaceTaskQueueHead">
        <div>
          <div className="workspaceTaskQueueEyebrow">Маршрут</div>
          <h2>{title}</h2>
        </div>
        {aside ? <div className="workspaceTaskQueueAside">{aside}</div> : null}
      </div>
      <div className="workspaceTaskQueueList">
        {items.map((item, index) => {
          const status = item.status || (index === 0 ? "active" : "todo");
          const content = (
            <>
              <div className="workspaceTaskQueueIndex">{String(index + 1).padStart(2, "0")}</div>
              <div className="workspaceTaskQueueCopy">
                <div className="workspaceTaskQueueTitleRow">
                  <strong>{item.label}</strong>
                  <span className={`workspaceTaskQueueStatus is-${status}`}>{STATUS_LABEL[status]}</span>
                </div>
                {item.meta ? <small>{item.meta}</small> : null}
              </div>
              {item.href ? <span className="workspaceTaskQueueAction">{item.actionLabel || "Открыть"}</span> : null}
            </>
          );

          return item.href ? (
            <Link key={item.key} className={`workspaceTaskQueueItem is-${status}`} to={item.href}>
              {content}
            </Link>
          ) : (
            <div key={item.key} className={`workspaceTaskQueueItem is-${status}`}>
              {content}
            </div>
          );
        })}
      </div>
      {activeItem ? (
        <div className={`workspaceTaskQueueFocus is-${activeItem.status || "active"}`}>
          <span>Сейчас</span>
          <strong>{activeItem.label}</strong>
          <p>{activeItem.description}</p>
          {activeItem.href ? (
            <Link to={activeItem.href} className="workspaceTaskQueueFocusAction">
              {activeItem.actionLabel || "Открыть"}
            </Link>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
