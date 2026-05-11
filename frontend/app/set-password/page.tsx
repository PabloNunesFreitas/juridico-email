"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function SetPasswordPage() {
  const router = useRouter();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("As senhas não coincidem");
      return;
    }
    if (newPassword.length < 6) {
      setError("A senha deve ter pelo menos 6 caracteres");
      return;
    }
    setLoading(true);
    try {
      await api.setPassword({ new_password: newPassword, confirm_password: confirmPassword });
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Erro ao definir senha");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold mb-1">Criar nova senha</h1>
        <p className="text-sm text-gray-500 mb-6">
          Seu acesso foi configurado com uma senha temporária. Defina uma senha pessoal para continuar.
        </p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-sm font-medium">Digite sua nova senha</label>
            <input
              className="input mt-1"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
              placeholder="Mínimo 6 caracteres"
            />
          </div>
          <div>
            <label className="text-sm font-medium">Confirme sua nova senha</label>
            <input
              className="input mt-1"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              placeholder="Repita a senha"
            />
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button className="btn-primary w-full" disabled={loading}>
            {loading ? "Salvando..." : "Salvar senha"}
          </button>
        </form>
      </div>
    </div>
  );
}
