import { FormEvent, useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../app/auth/AuthContext";
import AuthShell from "../components/auth/AuthShell";

export default function InviteAccept() {
  const { loading, firstPath, user, refresh } = useAuth();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const initialEmail = searchParams.get("email") || user?.email || "";
  const [email, setEmail] = useState(initialEmail);
  const [name, setName] = useState(user?.name || "");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const tokenError = useMemo(() => {
    if (!token) return "В ссылке отсутствует token приглашения.";
    return "";
  }, [token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSubmitting(true);
    setError("");
    try {
      await api("/platform/invites/accept", {
        method: "POST",
        body: JSON.stringify({
          token,
          email: email.trim(),
          name: name.trim(),
          password: password || undefined,
        }),
      });
      await refresh();
      setAccepted(true);
    } catch (err) {
      setError((err as Error).message || "Ошибка принятия приглашения");
    } finally {
      setSubmitting(false);
    }
  }

  if (!loading && accepted && !tokenError) {
    return <Navigate to={firstPath} replace />;
  }

  return (
    <AuthShell
      mode="invite"
      title="Принять приглашение"
      subtitle="Подтверди пользователя и войди в организацию по инвайт-ссылке."
      showModeTabs={false}
    >
      <form className="authForm authFormPremium" onSubmit={onSubmit}>
        <div className="authSectionLabel">Приглашение</div>
        <label className="authField">
          <span>Email</span>
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="ivan@company.ru" />
        </label>
        <label className="authField">
          <span>Имя</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Иван Петров" />
        </label>
        <label className="authField">
          <span>Пароль для нового аккаунта</span>
          <div className="authPasswordWrap">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              placeholder="Придумайте пароль"
            />
            <button
              type="button"
              className="authPasswordToggle"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
            >
              {showPassword ? "Скрыть" : "Показать"}
            </button>
          </div>
        </label>
        {tokenError ? <div className="authError">{tokenError}</div> : null}
        {error ? <div className="authError">{error}</div> : null}
        <button className="authPrimaryButton" type="submit" disabled={submitting || !!tokenError}>
          {submitting ? "Подключаем..." : "Принять приглашение"}
        </button>
      </form>
    </AuthShell>
  );
}
