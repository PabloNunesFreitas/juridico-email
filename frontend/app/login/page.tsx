"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { must_change_password } = await api.login(email, password);
      if (must_change_password) {
        router.push("/set-password");
      } else {
        router.push("/dashboard");
      }
    } catch (err: any) {
      setError(err.message || "Falha ao entrar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card w-full max-w-md p-8">
        <div className="flex justify-center mb-6">
          <Image src="/logo.png" alt="Andrade Alves Advogados" width={200} height={80} className="object-contain" priority />
        </div>
        <p className="text-sm text-gray-500 text-center mb-6">Gestão de E-mails Jurídicos</p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-sm font-medium">E-mail</label>
            <input className="input mt-1" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="text-sm font-medium">Senha</label>
            <input className="input mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button className="btn-primary w-full" disabled={loading}>
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
