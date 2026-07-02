"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://juridico-email.onrender.com";

export type Role = "ADMIN" | "USER";
export interface User { id: number; name: string; email: string; role: Role; active: boolean; must_change_password: boolean; theme: string | null; created_at: string; }
export interface UserCreated extends User { temp_password: string; }
export interface UserMini { id: number; name: string; email: string; }
export interface EmailAccount {
  id: number;
  provider: string;
  email_address: string;
  color: string;
  active: boolean;
  needs_reconnect: boolean;
  protected?: boolean;
}

export interface Folder {
  id: number;
  name: string;
  user_id: number;
  created_at: string;
  demand_count: number;
}

export interface CoAssignee { share_id: number; user: UserMini; }

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
  co_assignees: CoAssignee[];
  email_account: { id: number; email_address: string; color: string } | null;
  folder_id: number | null;
  archived: boolean;
  last_message_at: string;
  created_at: string;
}
export interface Attachment {
  id: number;
  filename: string;
  mime_type: string | null;
  size: number | null;
  external_attachment_id: string | null;
}
export interface Message {
  id: number;
  direction: string;
  sender_email: string;
  sender_name: string | null;
  recipient_emails: string | null;
  cc_emails: string | null;
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  received_at: string;
  has_attachments: boolean;
  attachments: Attachment[];
}
export interface Comment {
  id: number;
  demand_id: number;
  user_id: number;
  user_name: string;
  content: string;
  created_at: string;
}
export interface Notification {
  id: number;
  demand_id: number | null;
  type: string;
  message: string;
  read: boolean;
  responded: boolean;
  created_at: string;
}
export interface ChatMention {
  notification_id: number;
  demand_id: number;
  demand_subject: string;
  message: string;
  created_at: string;
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
  const isFormData = opts.body instanceof FormData;
  const headers: Record<string, string> = isFormData ? {} : { "Content-Type": "application/json", ...(opts.headers as any) };
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30_000);
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers, signal: controller.signal }).finally(() => clearTimeout(timeoutId));
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
  demandStats: () => request<{ total: number; unassigned: number; by_status: Record<string, number> }>(`/api/v1/demands/stats`),
  sharedDemands: () => request<Demand[]>("/api/v1/demands/shared"),
  shareDemand: (id: number, user_id: number, note?: string) =>
    request<{ ok: boolean }>(`/api/v1/demands/${id}/share`, { method: "POST", body: JSON.stringify({ user_id, note }) }),
  unshareDemand: (id: number, share_id: number) =>
    request<{ ok: boolean }>(`/api/v1/demands/${id}/share/${share_id}`, { method: "DELETE" }),
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
  replyDemand: (id: number, body_text: string, cc: string[] = [], to_emails?: string[], files?: File[]) => {
    const fd = new FormData();
    fd.append("body_text", body_text);
    fd.append("to_emails", JSON.stringify(to_emails ?? []));
    fd.append("cc", JSON.stringify(cc));
    (files ?? []).forEach(f => fd.append("files", f));
    return request<DemandDetail>(`/api/v1/demands/${id}/reply`, { method: "POST", body: fd });
  },
  archiveDemand: (id: number, folder_id: number) =>
    request<Demand>(`/api/v1/demands/${id}/archive?folder_id=${folder_id}`, { method: "POST" }),
  unarchiveDemand: (id: number) =>
    request<Demand>(`/api/v1/demands/${id}/unarchive`, { method: "POST" }),
  closeArchive: (id: number) =>
    request<Demand>(`/api/v1/demands/${id}/close-archive`, { method: "POST" }),
  reopenDemand: (id: number) =>
    request<Demand>(`/api/v1/demands/${id}/reopen`, { method: "POST" }),
  archivedDemands: (q?: string) =>
    request<Demand[]>(`/api/v1/demands/archived${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  archivedCount: () => request<{ count: number }>("/api/v1/demands/archived-count"),

  listFolders: () => request<Folder[]>("/api/v1/folders"),
  createFolder: (name: string) => request<Folder>("/api/v1/folders", { method: "POST", body: JSON.stringify({ name }) }),
  renameFolder: (id: number, name: string) => request<Folder>(`/api/v1/folders/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteFolder: (id: number) => request<void>(`/api/v1/folders/${id}`, { method: "DELETE" }),
  listFolderDemands: (id: number) => request<Demand[]>(`/api/v1/folders/${id}/demands`),

  listComments: (demandId: number) => request<Comment[]>(`/api/v1/demands/${demandId}/comments`),
  addComment: (demandId: number, content: string, mentions: number[] = []) =>
    request<Comment>(`/api/v1/demands/${demandId}/comments`, { method: "POST", body: JSON.stringify({ content, mentions }) }),

  listNotifications: () => request<Notification[]>("/api/v1/notifications"),
  unreadCount: () => request<{ count: number }>("/api/v1/notifications/unread-count"),
  markAllRead: () => request<{ ok: boolean }>("/api/v1/notifications/read-all", { method: "POST" }),
  markRead: (id: number) => request<{ ok: boolean }>(`/api/v1/notifications/${id}/read`, { method: "PATCH" }),
  chatMentions: () => request<ChatMention[]>("/api/v1/notifications/chat"),
  pendingMentions: () => request<number[]>("/api/v1/notifications/pending-mentions"),
  dismissMention: (id: number) => request<{ ok: boolean }>(`/api/v1/notifications/${id}/dismiss`, { method: "PATCH" }),

  setTheme: (theme: string) =>
    request<User>("/api/v1/auth/me/theme", { method: "PATCH", body: JSON.stringify({ theme }) }),

  downloadAttachment: (messageId: number, attId: number) =>
    `${API_URL}/api/v1/messages/${messageId}/attachments/${attId}/download`,

  // Busca o anexo COM o token (link <a> não envia Authorization) e devolve um blob.
  fetchAttachmentBlob: async (messageId: number, attId: number): Promise<Blob> => {
    const t = token();
    const res = await fetch(`${API_URL}/api/v1/messages/${messageId}/attachments/${attId}/download`, {
      headers: t ? { Authorization: `Bearer ${t}` } : {},
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.blob();
  },

  joinDemand: (id: number) =>
    request<Demand>(`/api/v1/demands/${id}/join`, { method: "POST" }),
  coAssign: (demandId: number, user_id: number) =>
    request<Demand>(`/api/v1/demands/${demandId}/co-assign`, { method: "POST", body: JSON.stringify({ user_id }) }),
  coUnassign: (demandId: number, shareId: number) =>
    request<Demand>(`/api/v1/demands/${demandId}/co-assign/${shareId}`, { method: "DELETE" }),
  composeEmail: (data: { to_emails: string[]; cc: string[]; subject: string; body_text: string; account_id?: number; files?: File[] }) => {
    const fd = new FormData();
    fd.append("to_emails", JSON.stringify(data.to_emails));
    fd.append("cc", JSON.stringify(data.cc));
    fd.append("subject", data.subject);
    fd.append("body_text", data.body_text);
    if (data.account_id) fd.append("account_id", String(data.account_id));
    (data.files ?? []).forEach(f => fd.append("files", f));
    return request<{ ok: boolean }>("/api/v1/demands/compose", { method: "POST", body: fd });
  },

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
