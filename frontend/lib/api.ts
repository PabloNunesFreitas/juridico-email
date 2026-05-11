"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Role = "ADMIN" | "USER";
export interface User { id: number; name: string; email: string; role: Role; active: boolean; must_change_password: boolean; created_at: string; }
export interface UserCreated extends User { temp_password: string; }
export interface UserMini { id: number; name: string; email: string; }
export interface EmailAccount {
  id: number;
  provider: string;
  email_address: string;
  color: string;
  active: boolean;
}

export interface Demand {
  id: number;
  sender_email: string;
  sender_name: string | null;
  subject: string | null;
  client_name: string | null;
  nup: string | null;
  bank: string | null;
  status: string;
  assigned_user: UserMini | null;
  email_account: { id: number; email_address: string; color: string } | null;
  last_message_at: string;
  created_at: string;
}
export interface Message {
  id: number;
  direction: string;
  sender_email: string;
  sender_name: string | null;
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  received_at: string;
  has_attachments: boolean;
}
export interface DemandDetail extends Demand { messages: Message[]; }
export interface AuditLog {
  id: number;
  demand_id: number | null;
  user_id: number | null;
  event_type: string;
  description: string | null;
  metadata_json: any;
  created_at: string;
}

function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(opts.headers as any) };
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("token");
    window.location.href = "/login";
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  async login(email: string, password: string): Promise<{ must_change_password: boolean }> {
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) throw new Error("E-mail ou senha inválidos");
    const data = await res.json();
    localStorage.setItem("token", data.access_token);
    return { must_change_password: data.must_change_password ?? false };
  },
  logout() {
    localStorage.removeItem("token");
    if (typeof window !== "undefined") window.location.href = "/login";
  },
  me: () => request<User>("/api/v1/auth/me"),

  listUsers: () => request<User[]>("/api/v1/users"),
  createUser: (data: { name: string; email: string; role: Role }) =>
    request<UserCreated>("/api/v1/users", { method: "POST", body: JSON.stringify(data) }),
  updateUser: (id: number, data: Partial<{ name: string; role: Role; active: boolean; password: string }>) =>
    request<User>(`/api/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deactivateUser: (id: number) => request<void>(`/api/v1/users/${id}`, { method: "DELETE" }),
  resetPassword: (id: number) =>
    request<{ temp_password: string; email: string }>(`/api/v1/users/${id}/reset-password`, { method: "POST" }),
  setPassword: (data: { new_password: string; confirm_password: string }) =>
    request<User>("/api/v1/auth/set-password", { method: "POST", body: JSON.stringify(data) }),

  syncEmail: () => request<{ new_demands: number; new_messages: number; scanned: number }>("/api/v1/email/sync", { method: "POST" }),

  listDemands: (params: Record<string, any> = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([_, v]) => v !== undefined && v !== "" && v !== null).map(([k, v]) => [k, String(v)])
    ).toString();
    return request<Demand[]>(`/api/v1/demands${qs ? "?" + qs : ""}`);
  },
  myDemands: (params: Record<string, any> = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([_, v]) => v !== undefined && v !== "" && v !== null).map(([k, v]) => [k, String(v)])
    ).toString();
    return request<Demand[]>(`/api/v1/demands/my${qs ? "?" + qs : ""}`);
  },
  unassignedDemands: (params: Record<string, any> = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([_, v]) => v !== undefined && v !== "" && v !== null).map(([k, v]) => [k, String(v)])
    ).toString();
    return request<Demand[]>(`/api/v1/demands/unassigned${qs ? "?" + qs : ""}`);
  },
  getDemand: (id: number) => request<DemandDetail>(`/api/v1/demands/${id}`),
  assignDemand: (id: number, user_id: number, bulk: boolean = false) =>
    request<Demand>(`/api/v1/demands/${id}/assign?bulk=${bulk}`, { method: "PATCH", body: JSON.stringify({ user_id }) }),
  assumeDemand: (id: number, bulk: boolean = false) =>
    request<Demand>(`/api/v1/demands/${id}/assume?bulk=${bulk}`, { method: "POST" }),
  unassignDemand: (id: number, keepRule: boolean = false, bulk: boolean = false) =>
    request<Demand>(`/api/v1/demands/${id}/unassign?keep_rule=${keepRule}&bulk=${bulk}`, { method: "POST" }),
  changeStatus: (id: number, status: string) =>
    request<Demand>(`/api/v1/demands/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
  updateDemand: (id: number, data: Partial<{ client_name: string; nup: string; bank: string; status: string }>) =>
    request<Demand>(`/api/v1/demands/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  demandLogs: (id: number) => request<AuditLog[]>(`/api/v1/demands/${id}/logs`),
  replyDemand: (id: number, body_text: string) =>
    request<DemandDetail>(`/api/v1/demands/${id}/reply`, { method: "POST", body: JSON.stringify({ body_text }) }),

  listLogs: (params: Record<string, any> = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([_, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])
    ).toString();
    return request<AuditLog[]>(`/api/v1/logs${qs ? "?" + qs : ""}`);
  },

  getEmailProvider: () => request<{ provider: string; email_address: string; active: boolean }>("/api/v1/settings/email-provider"),
  setEmailProvider: (data: { provider: string; email_address: string }) =>
    request("/api/v1/settings/email-provider", { method: "POST", body: JSON.stringify(data) }),

  getGmailCreds: () => request<{ client_id: string; client_secret_set: boolean }>("/api/v1/settings/credentials/gmail"),
  saveGmailCreds: (data: { client_id: string; client_secret: string }) =>
    request<{ client_id: string; client_secret_set: boolean }>("/api/v1/settings/credentials/gmail", { method: "POST", body: JSON.stringify(data) }),
  getOutlookCreds: () => request<{ client_id: string; client_secret_set: boolean; tenant_id: string }>("/api/v1/settings/credentials/outlook"),
  saveOutlookCreds: (data: { client_id: string; client_secret: string; tenant_id: string }) =>
    request<{ client_id: string; client_secret_set: boolean; tenant_id: string }>("/api/v1/settings/credentials/outlook", { method: "POST", body: JSON.stringify(data) }),

  oauthStart: (provider: "gmail" | "outlook", client_id_override?: string, client_secret_override?: string) =>
    request<{ authorize_url: string }>("/api/v1/email/oauth/start", { method: "POST", body: JSON.stringify({ provider, client_id_override, client_secret_override }) }),

  listAccounts: () => request<EmailAccount[]>("/api/v1/settings/accounts"),
  updateAccountColor: (id: number, color: string) =>
    request<EmailAccount>(`/api/v1/settings/accounts/${id}/color`, { method: "PATCH", body: JSON.stringify({ color }) }),
  deleteAccount: (id: number) => request<{ ok: boolean; demands_removed: number }>(`/api/v1/settings/accounts/${id}`, { method: "DELETE" }),
  oauthStatus: (provider: "gmail" | "outlook") =>
    request<{ provider: string; email_address: string; connected: boolean }>(`/api/v1/email/oauth/status?provider=${provider}`),
  oauthDisconnect: (provider: "gmail" | "outlook") =>
    request<{ ok: boolean; demands_removed: number }>(`/api/v1/email/oauth/disconnect?provider=${provider}`, { method: "POST" }),
  syncStatus: () => request<{
    running: boolean;
    started_at: string | null;
    finished_at: string | null;
    scanned: number;
    to_fetch: number;
    fetched: number;
    new_messages: number;
    new_demands: number;
    error: string | null;
    last_message: string | null;
  }>("/api/v1/email/sync/status"),
};

export const STATUSES = [
  "Caixa de Entrada", "Enviar resposta banco", "Enviar minuta assinada", "Pendências", "Erro",
  "Acordos realizados", "Solicitada proposta", "Proposta aceita", "Follow up", "Proposta com erro", "Minuta assinada",
];

export const BANKS = ["Banco do Brasil", "Caixa Econômica Federal", "Itaú", "Bradesco", "Santander", "Outros"];
