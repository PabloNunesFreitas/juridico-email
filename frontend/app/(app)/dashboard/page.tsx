"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Stats = { total: number; unassigned: number; by_status: Record<string, number> };

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    const s = await api.demandStats();
    setStats(s);
  }

  useEffect(() => { load(); }, []);

  async function sync() {
    setSyncing(true);
    setMsg(null);
    try {
      const r = await api.syncEmail();
      setMsg(`Sincronização concluída: ${r.new_demands} novas demandas, ${r.new_messages} mensagens.`);
      await load();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setSyncing(false);
    }
  }

  const byStatus: Record<string, number> = stats?.by_status ?? {};
  const unassigned = stats?.unassigned ?? 0;
  const total = stats?.total ?? 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button className="btn-primary" onClick={sync} disabled={syncing}>{syncing ? "Sincronizando..." : "Sincronizar e-mails"}</button>
      </div>
      {msg && <div className="card p-3 mb-4 text-sm">{msg}</div>}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Stat label="Total de demandas" value={total} />
        <Stat label="Não atribuídas" value={unassigned} />
        <Stat label="Em follow up" value={byStatus["Follow up"] || 0} />
        <Stat label="Acordos realizados" value={byStatus["Acordos realizados"] || 0} />
      </div>
      <div className="card p-4">
        <h2 className="font-semibold mb-3">Distribuição por status</h2>
        <div className="space-y-2">
          {Object.entries(byStatus).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between text-sm">
              <span>{k}</span>
              <span className="badge bg-blue-100 text-blue-800">{v}</span>
            </div>
          ))}
          {Object.keys(byStatus).length === 0 && <div className="text-sm text-gray-500">Sem demandas. Clique em "Sincronizar e-mails".</div>}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-gray-500 uppercase">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
    </div>
  );
}
