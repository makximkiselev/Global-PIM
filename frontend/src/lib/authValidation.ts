import { z } from "zod";

const requiredText = (message: string) => z.string().trim().min(1, message);

export const loginSchema = z.object({
  login: requiredText("Укажите логин или email"),
  password: requiredText("Введите пароль"),
});

export const registerSchema = z.object({
  organizationName: requiredText("Укажите название организации"),
  name: requiredText("Укажите имя администратора"),
  email: requiredText("Укажите email администратора").email("Введите корректный email"),
  password: z.string().min(8, "Пароль должен быть не короче 8 символов"),
});

export const inviteAcceptSchema = z.object({
  email: requiredText("Укажите email").email("Введите корректный email"),
  name: z.string().trim(),
  password: z.string().refine((value) => !value || value.length >= 8, "Пароль должен быть не короче 8 символов"),
});

const optionalEmail = z.string().trim().refine((value) => !value || z.email().safeParse(value).success, "Введите корректный email");
const optionalPassword = z.string().refine((value) => !value || value.length >= 8, "Пароль должен быть не короче 8 символов");

export const adminUserSchema = z.object({
  login: requiredText("Укажите логин пользователя"),
  email: optionalEmail,
  name: z.string().trim(),
  role_ids: z.array(z.string()).min(1, "Выберите хотя бы одну роль"),
  is_active: z.boolean(),
  password: optionalPassword,
});

export const adminCreateUserSchema = adminUserSchema.extend({
  password: z.string().min(8, "Пароль должен быть не короче 8 символов"),
});

export const adminRoleSchema = z.object({
  code: requiredText("Укажите код роли"),
  name: requiredText("Укажите название роли"),
  description: z.string().trim(),
  pages: z.array(z.string()),
  actions: z.array(z.string()),
});

export const adminResetPasswordSchema = z.object({
  password: optionalPassword,
});

export const changePasswordSchema = z.object({
  currentPassword: requiredText("Введите текущий пароль"),
  newPassword: z.string().min(8, "Новый пароль должен быть не короче 8 символов"),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
export type RegisterFormValues = z.infer<typeof registerSchema>;
export type InviteAcceptFormValues = z.infer<typeof inviteAcceptSchema>;
export type AdminUserFormValues = z.infer<typeof adminUserSchema>;
export type AdminRoleFormValues = z.infer<typeof adminRoleSchema>;
