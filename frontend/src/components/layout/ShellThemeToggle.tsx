import IconButton from "../ui/IconButton";
import ShellIcon from "./ShellIcon";
import { useTheme } from "../../app/theme/ThemeContext";

export default function ShellThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const nextThemeLabel = theme === "light" ? "Включить темную тему" : "Включить светлую тему";

  return (
    <IconButton
      className="shellThemeToggle"
      aria-label={nextThemeLabel}
      title={nextThemeLabel}
      onClick={toggleTheme}
    >
      <span className="shellThemeToggleIcon">
        <ShellIcon name={theme === "light" ? "moon" : "sun"} />
      </span>
    </IconButton>
  );
}
