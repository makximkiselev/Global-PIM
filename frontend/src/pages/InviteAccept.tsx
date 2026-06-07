import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Navigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../app/auth/AuthContext";
import AuthShell from "../components/auth/AuthShell";
import { InviteAcceptFormValues, inviteAcceptSchema } from "../lib/authValidation";

export default function InviteAccept() {
  const { loading, firstPath, user, refresh } = useAuth();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const initialEmail = searchParams.get("email") || user?.email || "";
  const [showPassword, setShowPassword] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [accepted, setAccepted] = useState(false);
  const {
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
    reset,
  } = useForm<InviteAcceptFormValues>({
    defaultValues: { email: initialEmail, name: user?.name || "", password: "" },
    resolver: zodResolver(inviteAcceptSchema),
  });

  const tokenError = useMemo(() => {
    if (!token) return "В ссылке отсутствует token приглашения.";
    return "";
  }, [token]);

  useEffect(() => {
    reset({ email: initialEmail, name: user?.name || "", password: "" });
  }, [initialEmail, reset, user?.name]);

  async function onSubmit(values: InviteAcceptFormValues) {
    if (!token) return;
    setSubmitError("");
    try {
      await api("/platform/invites/accept", {
        method: "POST",
        body: JSON.stringify({
          token,
          email: values.email.trim(),
          name: values.name.trim(),
          password: values.password || undefined,
        }),
      });
      await refresh();
      setAccepted(true);
    } catch (err) {
      setSubmitError((err as Error).message || "Ошибка принятия приглашения");
    }
  }

  if (!loading && accepted && !tokenError) {
    return <Navigate to={firstPath} replace />;
  }

  return (
    <AuthShell
      mode="invite"
      title="Принять приглашение"
      subtitle="Подтвердите пользователя и войдите в организацию по ссылке-приглашению."
      showModeTabs={false}
    >
      <form className="authForm authFormPremium" onSubmit={handleSubmit(onSubmit)}>
        <div className="authSectionLabel">Приглашение</div>
        <label className="authField">
          <span>Email</span>
          <input {...register("email")} autoComplete="email" placeholder="ivan@company.ru" />
        </label>
        {errors.email ? <div className="authError">{errors.email.message}</div> : null}
        <label className="authField">
          <span>Имя</span>
          <input {...register("name")} autoComplete="name" placeholder="Иван Петров" />
        </label>
        {errors.name ? <div className="authError">{errors.name.message}</div> : null}
        <label className="authField">
          <span>Пароль для нового аккаунта</span>
          <div className="authPasswordWrap">
            <input
              type={showPassword ? "text" : "password"}
              {...register("password")}
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
        {errors.password ? <div className="authError">{errors.password.message}</div> : null}
        {tokenError ? <div className="authError">{tokenError}</div> : null}
        {submitError ? <div className="authError">{submitError}</div> : null}
        <button className="authPrimaryButton" type="submit" disabled={isSubmitting || !!tokenError}>
          {isSubmitting ? "Подключаем..." : "Принять приглашение"}
        </button>
      </form>
    </AuthShell>
  );
}
