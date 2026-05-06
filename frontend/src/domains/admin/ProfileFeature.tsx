import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Field from "../../components/ui/Field";
import Modal from "../../components/ui/Modal";
import PageHeader from "../../components/ui/PageHeader";
import TextInput from "../../components/ui/TextInput";
import { api } from "../../lib/api";

const ROLE_LABELS: Record<string, string> = {
  org_owner: "Владелец",
  org_admin: "Администратор",
  org_editor: "Редактор",
  org_viewer: "Наблюдатель",
};

function roleLabel(code?: string | null) {
  return ROLE_LABELS[String(code || "")] || String(code || "Не указана");
}

function splitName(value?: string | null) {
  if (String(value || "").trim().toLowerCase() === "owner") {
    return { firstName: "Владелец", lastName: "" };
  }
  const parts = String(value || "").trim().split(/\s+/).filter(Boolean);
  return {
    firstName: parts[0] || "",
    lastName: parts.slice(1).join(" "),
  };
}

export default function ProfileFeature() {
  const navigate = useNavigate();
  const { user, roles, currentOrganization, logout, refresh } = useAuth();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordOk, setPasswordOk] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const { firstName, lastName } = useMemo(() => splitName(user?.name), [user?.name]);
  const roleNames = useMemo(() => {
    if (!user?.role_ids?.length) return [];
    return roles
      .filter((role) => user.role_ids.includes(role.id))
      .map((role) => role.name)
      .filter(Boolean);
  }, [roles, user?.role_ids]);

  const initials = (firstName || user?.login || user?.email || "SP")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

  async function submitPasswordChange() {
    setSavingPassword(true);
    setPasswordError("");
    setPasswordOk("");
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setPasswordOk("Пароль обновлен");
      await refresh();
    } catch (e) {
      setPasswordError((e as Error).message || "Ошибка смены пароля");
    } finally {
      setSavingPassword(false);
    }
  }

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
      navigate("/login", { replace: true });
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="page-shell profilePage page-shell-narrow">
      <PageHeader
        title="Профиль"
        subtitle="Личные данные текущего пользователя и быстрые действия аккаунта."
        actions={(
          <>
            <Button onClick={() => setShowPasswordModal(true)}>Сменить пароль</Button>
            <Button variant="danger" onClick={() => void handleLogout()} disabled={loggingOut}>
              {loggingOut ? "Выходим..." : "Выйти"}
            </Button>
          </>
        )}
      />

      <div className="profileWorkspace page-center">
        <Card className="profileHero">
          <div className="profileAvatar">{initials || "SP"}</div>
          <div className="profileHeroMain">
            <div className="profileEyebrow">Текущий пользователь</div>
            <h1>{firstName || lastName ? `${firstName}${lastName ? ` ${lastName}` : ""}` : user?.email || user?.login || "Пользователь"}</h1>
            <p>{currentOrganization?.name || "Организация не выбрана"}</p>
          </div>
          <Badge tone={user?.is_active ? "active" : "danger"}>{user?.is_active ? "Активен" : "Отключен"}</Badge>
        </Card>

        <div className="profileGrid">
          <Card title="Личные данные" className="profileCard">
            <div className="profileRows">
              <div>
                <span>Имя</span>
                <strong>{firstName || "Не указано"}</strong>
              </div>
              <div>
                <span>Фамилия</span>
                <strong>{lastName || "Не указана"}</strong>
              </div>
              <div>
                <span>Почта</span>
                <strong>{user?.email || "Не указана"}</strong>
              </div>
              <div>
                <span>Логин</span>
                <strong>{user?.login || "Не указан"}</strong>
              </div>
            </div>
          </Card>

          <Card title="Доступ" className="profileCard">
            <div className="profileRows">
              <div>
                <span>Организация</span>
                <strong>{currentOrganization?.name || "Не выбрана"}</strong>
              </div>
              <div>
                <span>Роль в организации</span>
                <strong>{roleLabel(currentOrganization?.membership_role)}</strong>
              </div>
              <div>
                <span>Роли доступа</span>
                <strong>{roleNames.length ? roleNames.join(", ") : "Не назначены"}</strong>
              </div>
            </div>
          </Card>
        </div>
      </div>

      <Modal
        open={showPasswordModal}
        onClose={() => setShowPasswordModal(false)}
        title="Смена пароля"
        subtitle="Введите текущий пароль и новый пароль для входа."
        width="compact"
      >
        <div className="authForm">
          <Field label="Текущий пароль">
            <TextInput type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          </Field>
          <Field label="Новый пароль">
            <TextInput type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          </Field>
          {passwordError ? <Alert tone="error">{passwordError}</Alert> : null}
          {passwordOk ? <Alert tone="success">{passwordOk}</Alert> : null}
          <div className="accessActions">
            <Button variant="primary" onClick={() => void submitPasswordChange()} disabled={savingPassword || !currentPassword || !newPassword}>
              {savingPassword ? "Сохраняем..." : "Сменить пароль"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
