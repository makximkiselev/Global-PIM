import { ReactNode } from "react";

type AuthMode = "login" | "register" | "invite";

type AuthShellProps = {
  mode: AuthMode;
  title: string;
  subtitle: string;
  children: ReactNode;
  onModeChange?: (mode: "login" | "register") => void;
  showModeTabs?: boolean;
};

const VALUE_POINTS = [
  {
    index: "01",
    title: "Инфо-модели и шаблоны",
    text: "Собирайте структуру карточек и фиксируйте единые правила заполнения.",
  },
  {
    index: "02",
    title: "Категории и сопоставление",
    text: "Привязывайте категории, атрибуты и источники так, чтобы каналам уходили корректные данные.",
  },
];

export default function AuthShell({
  mode,
  title,
  subtitle,
  children,
  onModeChange,
  showModeTabs = mode !== "invite",
}: AuthShellProps) {
  return (
    <div className="authPage authPagePremium">
      <div className="authLayout">
        <section className="authShowcase">
          <div className="authShowcaseInner">
            <div className="authShowcaseEyebrow">SmartPim</div>
            <div className="authShowcaseKicker">Каталог, контент, категории и каналы</div>
            <h1 className="authShowcaseTitle">Управляйте товарными данными в одном PIM</h1>
            <p className="authShowcaseText">
              Управляйте категориями, шаблонами, словарями, источниками и товарным контентом в одном PIM.
              Команда работает внутри своей организации и готовит данные к выгрузке без разрозненных таблиц.
            </p>

            <div className="authShowcaseSplit">
              <div className="authShowcaseSplitCard">
                <div className="authShowcaseSplitLabel">Фокус</div>
                <div className="authShowcaseSplitValue">Категории и контент</div>
              </div>
              <div className="authShowcaseSplitCard">
                <div className="authShowcaseSplitLabel">Контур</div>
                <div className="authShowcaseSplitValue">Источники и выгрузка</div>
              </div>
            </div>

            <div className="authFeatureList">
              {VALUE_POINTS.map((item) => (
                <div key={item.index} className="authFeatureRow">
                  <div className="authFeatureIndex">{item.index}</div>
                  <div className="authFeatureBody">
                    <div className="authFeatureTitle">{item.title}</div>
                    <div className="authFeatureText">{item.text}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="authPanel">
          <div className="authPanelEyebrow">Доступ</div>
          <h2 className="authPanelTitle">{title}</h2>
          <div className="authPanelSubtitle">{subtitle}</div>

          {showModeTabs ? (
            <div className="authModeTabs" role="tablist" aria-label="Режим доступа">
              <button
                type="button"
                className={`authModeTab${mode === "login" ? " is-active" : ""}`}
                aria-selected={mode === "login"}
                onClick={() => onModeChange?.("login")}
              >
                Вход
              </button>
              <button
                type="button"
                className={`authModeTab${mode === "register" ? " is-active" : ""}`}
                aria-selected={mode === "register"}
                onClick={() => onModeChange?.("register")}
              >
                Регистрация
              </button>
            </div>
          ) : null}

          <div className="authPanelBody">{children}</div>
        </section>
      </div>
    </div>
  );
}
