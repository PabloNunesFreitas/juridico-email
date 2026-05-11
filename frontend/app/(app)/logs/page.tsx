"use client";
import { useEffect, useState } from "react";
import { api, AuditLog } from "@/lib/api";

export default function LogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [type, setType] = useState("");

  async function load() {
    try {
      setLogs(await api.listLogs({ event_type: type || undefined, limit: 500 }));
    } catch {}
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [type]);

  // Auto-refresh: a cada 10s recarrega os logs
  useEffect(() => {
    const id = setInterval(() => { load(); }, 10_000);
    return () => clearInterval(id);
    /* eslint-disable-next-line */
  }, [type]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Logs</h1>
        <select className="input w-64" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Todos os eventos</option>
          {["DEMAND_CREATED", "DEMAND_ASSIGNED", "DEMAND_BULK_ASSIGNED", "DEMAND_AUTO_ASSIGNED", "DEMAND_ASSUMED", "DEMAND_UNASSIGNED", "DEMAND_STATUS_CHANGED",
            "MESSAGE_RECEIVED", "USER_CREATED", "USER_UPDATED", "USER_DEACTIVATED",
            "SYNC_COMPLETED", "SYNC_ERROR"].map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="text-left p-3">Data</th>
              <th className="text-left p-3">Evento</th>
              <th className="text-left p-3">Demanda</th>
              <th className="text-left p-3">Usuário</th>
              <th className="text-left p-3">Descrição</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-t">
                <td className="p-3 whitespace-nowrap">{new Date(l.created_at).toLocaleString()}</td>
                <td className="p-3"><span className="badge bg-gray-100 text-gray-700">{l.event_type}</span></td>
                <td className="p-3">{l.demand_id ?? "—"}</td>
                <td className="p-3">{l.user_id ?? "—"}</td>
                <td className="p-3">{l.description}</td>
              </tr>
            ))}
            {logs.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-gray-500">Sem logs.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
