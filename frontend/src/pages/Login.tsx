import { FormEvent, useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import AuthWorkspaceScene from "../components/auth/AuthWorkspaceScene";
import AuthViewTransitionLink from "../components/auth/AuthViewTransitionLink";

export default function Login() {
  const { authenticated, loading, login, firstPath } = useAuth();
  const [searchParams] = useSearchParams();
  const [loginValue, setLoginValue] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const sessionError = useMemo(() => {
    if (searchParams.get("denied") === "1") return "Отказ в доступе. Войдите заново.";
    if (searchParams.get("expired") === "1") return "Сессия истекла. Войдите снова.";
    return "";
  }, [searchParams]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(loginValue.trim(), password);
    } catch (err) {
      setError((err as Error).message || "Ошибка входа");
    } finally {
      setSubmitting(false);
    }
  }

  if (!loading && authenticated && !sessionError) {
    return <Navigate to={firstPath} replace />;
  }

  return (
    <AuthWorkspaceScene
      variant="light"
      badge="SmartPim"
      kicker="Каталог, контент, категории и каналы"
      title="Управляйте товарными данными как единой системой"
      lead="Категории, шаблоны, словари, источники и контент собираются в одном рабочем пространстве. Команда работает в общей структуре и публикует данные без ручной сборки по таблицам."
      note="Один контур для структуры, контента и подготовки к выгрузке."
      visualTop={{ label: "Шаблоны", title: "Контролируемые поля" }}
      visualBottom={{ label: "Категории", title: "Единая структура" }}
      cardEyebrow="Доступ"
      cardTitle="Вход пользователя"
      cardLead="Вход в рабочее пространство организации."
      footer={
        <div className="authCardFooter">
          <span>Нужна новая организация?</span>
          <AuthViewTransitionLink to="/register" className="authInlineLink">
            Создать пространство
          </AuthViewTransitionLink>
        </div>
      }
    >
      <form className="authPanelForm" onSubmit={onSubmit}>
        <label className="authPanelField">
          <span>Логин или email</span>
          <input
            value={loginValue}
            onChange={(e) => setLoginValue(e.target.value)}
            autoComplete="username"
            placeholder="Например, owner@company.ru"
          />
        </label>

        <label className="authPanelField">
          <span>Пароль</span>
          <div className="authPanelPassword">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="Введите пароль"
            />
            <button
              type="button"
              className="authPanelPasswordToggle"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
            >
              {showPassword ? "Скрыть" : "Показать"}
            </button>
          </div>
        </label>

        {sessionError ? <div className="authPanelError">{sessionError}</div> : null}
        {error ? <div className="authPanelError">{error}</div> : null}

        <button className="authPanelSubmit" type="submit" disabled={submitting}>
          {submitting ? "Входим..." : "Войти"}
        </button>
      </form>
    </AuthWorkspaceScene>
  );
}
