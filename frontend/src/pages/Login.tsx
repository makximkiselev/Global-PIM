import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import AuthWorkspaceScene from "../components/auth/AuthWorkspaceScene";
import AuthViewTransitionLink from "../components/auth/AuthViewTransitionLink";
import { LoginFormValues, loginSchema } from "../lib/authValidation";

export default function Login() {
  const { authenticated, loading, login, firstPath } = useAuth();
  const [searchParams] = useSearchParams();
  const [showPassword, setShowPassword] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const {
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
  } = useForm<LoginFormValues>({
    defaultValues: { login: "", password: "" },
    resolver: zodResolver(loginSchema),
  });

  const sessionError = useMemo(() => {
    if (searchParams.get("denied") === "1") return "Отказ в доступе. Войдите заново.";
    if (searchParams.get("expired") === "1") return "Сессия истекла. Войдите снова.";
    return "";
  }, [searchParams]);

  async function onSubmit(values: LoginFormValues) {
    setSubmitError("");
    try {
      await login(values.login.trim(), values.password);
    } catch (err) {
      setSubmitError((err as Error).message || "Ошибка входа");
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
      <form className="authPanelForm" onSubmit={handleSubmit(onSubmit)}>
        <label className="authPanelField">
          <span>Логин или email</span>
          <input
            {...register("login")}
            autoComplete="username"
            placeholder="Например, owner@company.ru"
          />
        </label>
        {errors.login ? <div className="authPanelError">{errors.login.message}</div> : null}

        <label className="authPanelField">
          <span>Пароль</span>
          <div className="authPanelPassword">
            <input
              type={showPassword ? "text" : "password"}
              {...register("password")}
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
        {errors.password ? <div className="authPanelError">{errors.password.message}</div> : null}

        {sessionError ? <div className="authPanelError">{sessionError}</div> : null}
        {submitError ? <div className="authPanelError">{submitError}</div> : null}

        <button className="authPanelSubmit" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Входим..." : "Войти"}
        </button>
      </form>
    </AuthWorkspaceScene>
  );
}
