"use client";
import { useEffect, useState } from "react";
import { api, User, Role } from "@/lib/api";

interface TempCredModal {
  email: string;
  temp_password: string;
  action: "criado" | "redefinido";
}

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("USER");
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<TempCredModal | null>(null);
  const [copied, setCopied] = useState(false);

  async function load() { setUsers(await api.listUsers()); }
  useEffect(() => { load(); }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await api.createUser({ name, email, role });
      setName(""); setEmail(""); setRole("USER"); setShowForm(false);
      setModal({ email: created.email, temp_password: created.temp_password, action: "criado" });
      await load();
    } catch (err: any) { setError(err.message); }
  }

  async function handleReset(u: User) {
    if (!confirm(`Redefinir senha de ${u.name}? O usuário receberá uma senha temporária.`)) return;
    try {
      const res = await api.resetPassword(u.id);
      setModal({ email: res.email, temp_password: res.temp_password, action: "redefinido" });
    } catch (err: any) { alert(err.message); }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function toggleActive(u: User) { await api.updateUser(u.id, { active: !u.active }); await load(); }
  async function changeRole(u: User, r: Role) { await api.updateUser(u.id, { role: r }); await load(); }

  return (
    <div>
      {/* Modal de credenciais temporárias */}
      {modal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="card w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-bold">
              {modal.action === "criado" ? "Usuário criado!" : "Senha redefinida!"}
            </h2>
            <p className="text-sm text-gray-600">
              Compartilhe estas credenciais com o usuário. Ele será obrigado a criar uma nova senha no primeiro acesso.
            </p>
            <div className="bg-gray-50 rounded p-3 space-y-2 text-sm">
              <div><span className="font-medium">E-mail:</span> {modal.email}</div>
              <div className="flex items-center gap-2">
                <span className="font-medium">Senha temporária:</span>
                <code className="bg-white border rounded px-2 py-0.5 font-mono">{modal.temp_password}</code>
                <button
                  className="btn-secondary text-xs px-2 py-1"
                  onClick={() => copyToClipboard(modal.temp_password)}
                >
                  {copied ? "Copiado!" : "Copiar"}
                </button>
              </div>
            </div>
            <button className="btn-primary w-full" onClick={() => { setModal(null); setCopied(false); }}>
              Fechar
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Usuários</h1>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancelar" : "Novo usuário"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card p-4 mb-4 grid grid-cols-1 md:grid-cols-4 gap-3">
          <input className="input" placeholder="Nome" value={name} onChange={(e) => setName(e.target.value)} required />
          <input className="input" placeholder="E-mail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="USER">Usuário</option>
            <option value="ADMIN">Admin</option>
          </select>
          <button className="btn-primary" type="submit">Criar</button>
          {error && <div className="md:col-span-4 text-sm text-red-600">{error}</div>}
          <p className="md:col-span-4 text-xs text-gray-500">A senha temporária será gerada automaticamente e exibida após a criação.</p>
        </form>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="text-left p-3">Nome</th>
              <th className="text-left p-3">E-mail</th>
              <th className="text-left p-3">Perfil</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Senha</th>
              <th className="text-left p-3"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t">
                <td className="p-3">
                  {u.name}
                  {u.must_change_password && (
                    <span className="ml-2 text-xs bg-yellow-100 text-yellow-800 rounded px-1">pendente</span>
                  )}
                </td>
                <td className="p-3">{u.email}</td>
                <td className="p-3">
                  <select className="input w-32" value={u.role} onChange={(e) => changeRole(u, e.target.value as Role)}>
                    <option value="USER">Usuário</option>
                    <option value="ADMIN">Admin</option>
                  </select>
                </td>
                <td className="p-3">
                  <span className={`badge ${u.active ? "bg-green-100 text-green-800" : "bg-gray-200 text-gray-700"}`}>
                    {u.active ? "Ativo" : "Inativo"}
                  </span>
                </td>
                <td className="p-3">
                  <button className="btn-secondary text-xs" onClick={() => handleReset(u)}>
                    Redefinir senha
                  </button>
                </td>
                <td className="p-3">
                  <button className="btn-secondary" onClick={() => toggleActive(u)}>
                    {u.active ? "Desativar" : "Ativar"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
