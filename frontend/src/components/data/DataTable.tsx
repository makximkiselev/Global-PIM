import { CSSProperties, ReactNode } from "react";

type Column<T> = {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty: string;
  className?: string;
  gridTemplate?: string;
};

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
  className = "",
  gridTemplate,
}: DataTableProps<T>) {
  const style = gridTemplate ? ({ gridTemplateColumns: gridTemplate } as CSSProperties) : undefined;

  return (
    <div className={`dataTable${className ? ` ${className}` : ""}`}>
      <div className="dataTableHead" style={style}>
        {columns.map((column) => (
          <span key={column.key}>{column.label}</span>
        ))}
      </div>

      {rows.length ? (
        rows.map((row) => (
          <div key={rowKey(row)} className="dataTableRow" style={style}>
            {columns.map((column) => (
              <div key={column.key}>{column.render(row)}</div>
            ))}
          </div>
        ))
      ) : (
        <div className="dataTableEmpty">{empty}</div>
      )}
    </div>
  );
}
