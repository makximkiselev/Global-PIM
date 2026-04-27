import { FormEvent, useMemo, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../app/auth/AuthContext";
import AuthShell from "../components/auth/AuthShell";

type AuthEntryProps = {
  initialMode?: "login" | "register";
};

export default function AuthEntry({ initialMode = "login" }: AuthEntryProps) {
  const { authenticated, loading, login, firstPath, refresh } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<"login" | "register">(initialMode);

  const [loginValue, setLoginValue] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [loginSubmitting, setLoginSubmitting] = useState(false);

  const [registerEmail, setRegisterEmail] = useState("");
  const [registerName, setRegisterName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [showRegisterPassword, setShowRegisterPassword] = useState(false);
  const [registerError, setRegisterError] = useState("");
  const [registerSubmitting, setRegisterSubmitting] = useState(false);

  const sessionError = useMemo(() => {
    if (searchParams.get("denied") === "1") return "Отказ в доступе. Войдите заново.";
    if (searchParams.get("expired") === "1") return "Сессия истекла. Войдите снова.";
    return "";
  }, [searchParams]);

  async function onLoginSubmit(e: FormEvent) {
    e.preventDefault();
    setLoginSubmitting(true);
    setLoginError("");
    try {
      await login(loginValue.trim(), loginPassword);
    } catch (err) {
      setLoginError((err as Error).message || "Ошибка входа");
    } finally {
      setLoginSubmitting(false);
    }
  }

  async function onRegisterSubmit(e: FormEvent) {
    e.preventDefault();
    setRegisterSubmitting(true);
    setRegisterError("");
    try {
      await api("/platform/register", {
        method: "POST",
        body: JSON.stringify({
          email: registerEmail.trim(),
          password: registerPassword,
          name: registerName.trim(),
          organization_name: organizationName.trim(),
        }),
      });
      await refresh();
    } catch (err) {
      setRegisterError((err as Error).message || "Ошибка регистрации");
    } finally {
      setRegisterSubmitting(false);
    }
  }

  function activateMode(nextMode: "login" | "register") {
    setMode(nextMode);
    navigate(nextMode === "login" ? "/" : "/register", { replace: true });
  }

  if (!loading && authenticated && !sessionError) {
    return <Navigate to={firstPath} replace />;
  }

  const title = mode === "login" ? "Вход пользователя" : "Регистрация организации";
  const subtitle =
    mode === "login"
      ? "Доступ к организациям, аналитике, контенту и рабочим контурам PIM."
      : "Создай первую организацию, зафиксируй администратора и открой рабочее пространство.";

  return (
    <AuthShell mode={mode} title={title} subtitle={subtitle} onModeChange={activateMode}>
      {mode === "login" ? (
        <form className="authForm authFormPremium" onSubmit={onLoginSubmit}>
          <div className="authSectionLabel">Учетные данные</div>
          <label className="authField">
            <span>Логин или email</span>
            <input
              value={loginValue}
              onChange={(e) => setLoginValue(e.target.value)}
              autoComplete="username"
              placeholder="Например, manager или owner@company.ru"
            />
          </label>
          <label className="authField">
            <span>Пароль</span>
            <div className="authPasswordWrap">
              <input
                type={showLoginPassword ? "text" : "password"}
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="Введите пароль"
              />
              <button
                type="button"
                className="authPasswordToggle"
                onClick={() => setShowLoginPassword((value) => !value)}
                aria-label={showLoginPassword ? "Скрыть пароль" : "Показать пароль"}
              >
                {showLoginPassword ? "Скрыть" : "Показать"}
              </button>
            </div>
          </label>
          {sessionError ? <div className="authError">{sessionError}</div> : null}
          {loginError ? <div className="authError">{loginError}</div> : null}
          <button className="authPrimaryButton" type="submit" disabled={loginSubmitting}>
            {loginSubmitting ? "Входим..." : "Войти"}
          </button>
        </form>
      ) : (
        <form className="authForm authFormPremium" onSubmit={onRegisterSubmit}>
          <div className="authSectionLabel">Организация</div>
          <label className="authField">
            <span>Название организации</span>
            <input
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              autoComplete="organization"
              placeholder="Например, Global Trade"
            />
          </label>

          <div className="authSectionLabel authSectionLabelTight">Первый администратор</div>
          <label className="authField">
            <span>Имя администратора</span>
            <input
              value={registerName}
              onChange={(e) => setRegisterName(e.target.value)}
              autoComplete="name"
              placeholder="Иван Петров"
            />
          </label>
          <label className="authField">
            <span>Email администратора</span>
            <input
              value={registerEmail}
              onChange={(e) => setRegisterEmail(e.target.value)}
              autoComplete="email"
              placeholder="ivan@company.ru"
            />
          </label>
          <label className="authField">
            <span>Пароль</span>
            <div className="authPasswordWrap">
              <input
                type={showRegisterPassword ? "text" : "password"}
                value={registerPassword}
                onChange={(e) => setRegisterPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="Придумайте пароль"
              />
              <button
                type="button"
                className="authPasswordToggle"
                onClick={() => setShowRegisterPassword((value) => !value)}
                aria-label={showRegisterPassword ? "Скрыть пароль" : "Показать пароль"}
              >
                {showRegisterPassword ? "Скрыть" : "Показать"}
              </button>
            </div>
          </label>

          {registerError ? <div className="authError">{registerError}</div> : null}
          <button className="authPrimaryButton" type="submit" disabled={registerSubmitting}>
            {registerSubmitting ? "Создаем организацию..." : "Создать организацию"}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
