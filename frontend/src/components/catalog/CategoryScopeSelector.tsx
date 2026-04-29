export type CategoryScopeMode = "all" | "branch" | "category";

type CategoryScopeSelectorProps = {
  mode: CategoryScopeMode;
  categorySelected: boolean;
  onModeChange: (mode: CategoryScopeMode) => void;
  className?: string;
};

const OPTIONS: Array<{
  mode: CategoryScopeMode;
  label: string;
  title: string;
  needsCategory?: boolean;
}> = [
  {
    mode: "all",
    label: "Весь каталог",
    title: "Все товары каталога",
  },
  {
    mode: "branch",
    label: "Вся ветка",
    title: "Выбранная категория и все вложенные разделы",
    needsCategory: true,
  },
  {
    mode: "category",
    label: "Только категория",
    title: "Только выбранная категория без вложенных разделов",
    needsCategory: true,
  },
];

export default function CategoryScopeSelector({
  mode,
  categorySelected,
  onModeChange,
  className = "",
}: CategoryScopeSelectorProps) {
  return (
    <div className={`categoryScopeSelector${className ? ` ${className}` : ""}`} aria-label="Область выбора">
      {OPTIONS.map((option) => {
        const disabled = !!option.needsCategory && !categorySelected;
        return (
          <button
            key={option.mode}
            className={`categoryScopeOption${mode === option.mode ? " isActive" : ""}`}
            type="button"
            onClick={() => onModeChange(option.mode)}
            disabled={disabled}
            title={disabled ? "Сначала выбери категорию" : option.title}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
