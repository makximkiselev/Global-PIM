import { ReactNode } from "react";

type DataListProps<T> = {
  title?: string;
  items: T[];
  renderItem: (item: T) => ReactNode;
  empty: string;
  className?: string;
};

export default function DataList<T>({
  title,
  items,
  renderItem,
  empty,
  className = "",
}: DataListProps<T>) {
  return (
    <div className={`dataList${className ? ` ${className}` : ""}`}>
      {title ? <div className="dataListTitle">{title}</div> : null}
      <div className="dataListStack">
        {items.length ? items.map(renderItem) : <div className="dataListEmpty">{empty}</div>}
      </div>
    </div>
  );
}
