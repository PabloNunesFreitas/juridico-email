"use client";
import { useEffect, useState } from "react";
import { api, AuditLog } from "@/lib/api";

const EVENT_LABELS: Record<string, string> = {
  DEMAND_CREATED: "Demanda criada",
  DEMAND_ASSIGNED: "Demanda atribuída",
  DEMAND_BULK_ASSIGNED: "Atribuição em lote",
  DEMAND_AUTO_ASSIGNED: "Atribuição automática",
  DEMAND_ASSUMED: "Demanda assumida",
  DEMAND_UNASSIGNED: "Responsável removido",
  DEMAND_STATUS_CHANGED: "Status alterado",
  MESSAGE_RECEIVED: "Mensagem recebida",
  USER_CREATED: "Usuário criado",
  USER_UPDATED: "Usuário atualizado",
  USER_DEACTIVATED: "Usuário desativado",
  SYNC_COMPLETED: "Sincronização concluída",
  SYNC_ERROR: "Erro na sincronização",
  OAUTH_CONNECTED: "Conta conectada",
  REPLY_SENT: "Resposta enviada",
  COMMENT_ADDED: "Comentário adicionado",
  DEMAND_ARCHIVED: "Demanda arquivada",
  DEMAND_MOVED_TO_FOLDER: "Movida para pasta",
};

export default function LogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [type, setType] = useState("");

  async function load() {
    try {
      setLogs(await api.listLogs({ event_type: type || undefined, limit: 500 }));
    } catch {}
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [type]);

  useEffect(() => {
    const id = setInterval(() => { load(); }, 10_000);
    return () => clearInterval(id);
    /* eslint-disable-next-line */
  }, [type]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h1 className="text-xl md:text-2xl font-bold">Logs</h1>
        <select className="input w-64" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Todos os eventos</option>
          {Object.entries(EVENT_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </div>
      <div className="card overflow-hidden overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="text-left p-3 whitespace-nowrap">Data</th>
              <th className="text-left p-3 whitespace-nowrap">Evento</th>
              <th className="text-left p-3 whitespace-nowrap">Demanda</th>
              <th className="text-left p-3 whitespace-nowrap">Usuário</th>
              <th className="text-left p-3">Descrição</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-t">
                <td className="p-3 whitespace-nowrap text-xs text-gray-500">{new Date(l.created_at).toLocaleString("pt-BR")}</td>
                <td className="p-3">
                  <span className="badge bg-gray-100 text-gray-700 whitespace-nowrap">
                    {EVENT_LABELS[l.event_type] ?? l.event_type}
                  </span>
                </td>
                <td className="p-3 text-center">{l.demand_id ?? "—"}</td>
                <td className="p-3 text-center">{l.user_id ?? "—"}</td>
                <td className="p-3 text-gray-700">{l.description}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-gray-500">Sem logs.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
