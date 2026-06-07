import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../app/auth/AuthContext";
import AuthWorkspaceScene from "../components/auth/AuthWorkspaceScene";
import AuthViewTransitionLink from "../components/auth/AuthViewTransitionLink";
import { RegisterFormValues, registerSchema } from "../lib/authValidation";

export default function Register() {
  const { authenticated, loading, firstPath, refresh } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const {
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
  } = useForm<RegisterFormValues>({
    defaultValues: { email: "", name: "", organizationName: "", password: "" },
    resolver: zodResolver(registerSchema),
  });

  async function onSubmit(values: RegisterFormValues) {
    setSubmitError("");
    try {
      await api("/platform/register", {
        method: "POST",
        body: JSON.stringify({
          email: values.email.trim(),
          password: values.password,
          name: values.name.trim(),
          organization_name: values.organizationName.trim(),
        }),
      });
      await refresh();
    } catch (err) {
      setSubmitError((err as Error).message || "Ошибка регистрации");
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
      <form className="authPanelForm authPanelFormRegister" onSubmit={handleSubmit(onSubmit)}>
        <label className="authPanelField authPanelFieldLight">
          <span>Название организации</span>
          <input
            {...register("organizationName")}
            autoComplete="organization"
            placeholder="Например, Global Trade"
          />
        </label>
        {errors.organizationName ? <div className="authPanelError authPanelErrorLight">{errors.organizationName.message}</div> : null}

        <label className="authPanelField authPanelFieldLight">
          <span>Имя администратора</span>
          <input
            {...register("name")}
            autoComplete="name"
            placeholder="Иван Петров"
          />
        </label>
        {errors.name ? <div className="authPanelError authPanelErrorLight">{errors.name.message}</div> : null}

        <label className="authPanelField authPanelFieldLight">
          <span>Email администратора</span>
          <input
            {...register("email")}
            autoComplete="email"
            placeholder="owner@company.ru"
          />
        </label>
        {errors.email ? <div className="authPanelError authPanelErrorLight">{errors.email.message}</div> : null}

        <label className="authPanelField authPanelFieldLight">
          <span>Пароль</span>
          <div className="authPanelPassword">
            <input
              type={showPassword ? "text" : "password"}
              {...register("password")}
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
        {errors.password ? <div className="authPanelError authPanelErrorLight">{errors.password.message}</div> : null}

        {submitError ? <div className="authPanelError authPanelErrorLight">{submitError}</div> : null}

        <button className="authPanelSubmit authPanelSubmitLight" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Создаем организацию..." : "Создать организацию"}
        </button>
      </form>
    </AuthWorkspaceScene>
  );
}
