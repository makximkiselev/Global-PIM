import { FormEvent, useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";

export default function Login() {
  const { authenticated, loading, login, firstPath } = useAuth();
  const [searchParams] = useSearchParams();
  const [loginValue, setLoginValue] = useState("");
  const [password, setPassword] = useState("");
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
    <div className="authPage">
      <div className="authCard">
        <div className="authHeader">
          <div className="authTitle">Вход в PIM</div>
          <div className="authSubtitle">Авторизация пользователей и управление доступом.</div>
        </div>
        <form className="authForm" onSubmit={onSubmit}>
          <label className="authField">
            <span>Логин</span>
            <input value={loginValue} onChange={(e) => setLoginValue(e.target.value)} autoComplete="username" />
          </label>
          <label className="authField">
            <span>Пароль</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          {sessionError ? <div className="authError">{sessionError}</div> : null}
          {error ? <div className="authError">{error}</div> : null}
          <button className="btn primary authSubmit" type="submit" disabled={submitting}>
            {submitting ? "Входим..." : "Войти"}
          </button>
        </form>
      </div>
    </div>
  );
}
