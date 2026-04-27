import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../app/auth/AuthContext";
import AuthWorkspaceScene from "../components/auth/AuthWorkspaceScene";
import AuthViewTransitionLink from "../components/auth/AuthViewTransitionLink";

export default function Register() {
  const { authenticated, loading, firstPath, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api("/platform/register", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          password,
          name: name.trim(),
          organization_name: organizationName.trim(),
        }),
      });
      await refresh();
    } catch (err) {
      setError((err as Error).message || "Ошибка регистрации");
    } finally {
      setSubmitting(false);
    }
  }

  if (!loading && authenticated) {
    return <Navigate to={firstPath} replace />;
  }

  return (
    <AuthWorkspaceScene
      variant="dark"
      badge="SmartPim"
      kicker="Новая организация, команда и рабочий контур"
      title="Создайте пространство для своей команды"
      lead="Организация создается сразу вместе с первым администратором. После входа вы сможете добавить сотрудников, раздать роли и развернуть рабочий контур PIM под свою структуру."
      note="Один контур для команды, ролей и структуры данных."
      visualTop={{ label: "Owner access", title: "Первый администратор" }}
      visualBottom={{ label: "Workspace", title: "Организация и команда" }}
      cardEyebrow="Новая организация"
      cardTitle="Регистрация"
      cardLead="После регистрации вы станете владельцем организации и сможете пригласить команду."
      footer={
        <div className="authCardFooter authCardFooterRegister">
          <span>Уже есть доступ?</span>
          <AuthViewTransitionLink to="/" className="authInlineLink">
            Вернуться ко входу
          </AuthViewTransitionLink>
        </div>
      }
    >
      <form className="authPanelForm authPanelFormRegister" onSubmit={onSubmit}>
        <label className="authPanelField authPanelFieldLight">
          <span>Название организации</span>
          <input
            value={organizationName}
            onChange={(e) => setOrganizationName(e.target.value)}
            autoComplete="organization"
            placeholder="Например, Global Trade"
          />
        </label>

        <label className="authPanelField authPanelFieldLight">
          <span>Имя администратора</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            placeholder="Иван Петров"
          />
        </label>

        <label className="authPanelField authPanelFieldLight">
          <span>Email администратора</span>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="owner@company.ru"
          />
        </label>

        <label className="authPanelField authPanelFieldLight">
          <span>Пароль</span>
          <div className="authPanelPassword">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              placeholder="Придумайте пароль"
            />
            <button
              type="button"
              className="authPanelPasswordToggle authPanelPasswordToggleLight"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
            >
              {showPassword ? "Скрыть" : "Показать"}
            </button>
          </div>
        </label>

        {error ? <div className="authPanelError authPanelErrorLight">{error}</div> : null}

        <button className="authPanelSubmit authPanelSubmitLight" type="submit" disabled={submitting}>
          {submitting ? "Создаем организацию..." : "Создать организацию"}
        </button>
      </form>
    </AuthWorkspaceScene>
  );
}
