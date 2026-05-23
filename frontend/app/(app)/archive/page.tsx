"use client";
import { useEffect, useState } from "react";
import { api, Demand, DemandDetail } from "@/lib/api";
import { toast } from "@/lib/toast";

export default function ArchivePage() {
  const [demands, setDemands] = useState<Demand[]>([]);
  const [selected, setSelected] = useState<DemandDetail | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reopening, setReopening] = useState(false);

  async function loadDemands(q?: string) {
    setLoading(true);
    try {
      const data = await api.archivedDemands(q);
      setDemands(data);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  useEffect(() => {
    const t = setTimeout(() => loadDemands(search.trim() || undefined), 350);
    return () => clearTimeout(t);
  }, [search]);

  async function openDemand(d: Demand) {
    try {
      const detail = await api.getDemand(d.id);
      setSelected(detail);
    } catch (e: any) { setError(e.message); }
  }

  async function reopen(d: Demand) {
    if (!confirm(`Reabrir "${d.subject || d.sender_email}"?\nA demanda voltará para a caixa de entrada.`)) return;
    setReopening(true);
    try {
      await api.reopenDemand(d.id);
      setDemands(prev => prev.filter(x => x.id !== d.id));
      if (selected?.id === d.id) setSelected(null);
      toast("Demanda reaberta com sucesso.", "success");
      window.dispatchEvent(new Event("archivechange"));
    } catch (e: any) { toast(e.message, "error"); }
    setReopening(false);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-2xl font-bold">📦 Arquivo Morto</h1>
          <p className="text-sm text-gray-500 mt-0.5">Casos finalizados e encerrados</p>
        </div>
        <div className="relative">
          <input
            className="input w-72 pr-8"
            placeholder="Buscar no arquivo morto..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700 text-sm">×</button>
          )}
        </div>
      </div>

      {error && <div className="card p-3 mb-3 text-sm text-red-700 bg-red-50">{error}</div>}

      <div className="grid grid-cols-12 gap-4 h-[calc(100vh-160px)]">
        {/* Lista */}
        <div className="col-span-5 card overflow-y-auto flex flex-col">
          {loading && <div className="p-4 text-sm text-gray-400">Carregando...</div>}
          {!loading && demands.length === 0 && (
            <div className="p-6 text-sm text-gray-400">
              {search ? "Nenhum resultado para essa busca." : "Nenhum caso arquivado ainda."}
            </div>
          )}
          <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
            {demands.map(d => (
              <div
                key={d.id}
                onClick={() => openDemand(d)}
                className={`flex cursor-pointer hover:bg-gray-50 ${selected?.id === d.id ? "bg-blue-50" : ""}`}
              >
                <div style={{ width: 4, flexShrink: 0, backgroundColor: d.email_account?.color ?? "#9ca3af" }} />
                <div className="flex-1 min-w-0 px-3 py-3">
                  <div className="flex justify-between items-start gap-2">
                    <div className="font-medium text-sm truncate text-gray-700">{d.sender_name || d.sender_email}</div>
                    <div className="text-xs text-gray-400 shrink-0">{new Date(d.last_message_at).toLocaleDateString()}</div>
                  </div>
                  <div className="text-xs text-gray-500 truncate mt-0.5">{d.subject || "(sem assunto)"}</div>
                  <div className="flex gap-1 mt-1.5 flex-wrap">
                    <span className="badge bg-gray-100 text-gray-500">{d.status}</span>
                    {d.assigned_user && <span className="badge bg-blue-50 text-blue-700">{d.assigned_user.name}</span>}
                    {d.bank && <span className="badge bg-amber-50 text-amber-700">{d.bank}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Detalhe */}
        <div className="col-span-7 card overflow-y-auto">
          {!selected ? (
            <div className="p-8 text-center text-gray-400 text-sm">
              <div className="text-4xl mb-3">📦</div>
              <p>Selecione uma demanda para ver os detalhes.</p>
            </div>
          ) : (
            <div className="p-4 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-base font-semibold text-gray-800">{selected.subject || "(sem assunto)"}</h2>
                  <p className="text-sm text-gray-500 mt-0.5">De: {selected.sender_name || ""} &lt;{selected.sender_email}&gt;</p>
                </div>
                <button
                  className="btn-primary text-xs shrink-0 disabled:opacity-50"
                  onClick={() => reopen(selected)}
                  disabled={reopening}
                  title="Restaura para caixa de entrada"
                >
                  ↩ Reabrir caso
                </button>
              </div>

              <div className="grid grid-cols-3 gap-2 text-xs">
                {selected.client_name && <InfoBox label="Cliente" value={selected.client_name} />}
                {selected.nup && <InfoBox label="NUP" value={selected.nup} />}
                {selected.bank && <InfoBox label="Banco" value={selected.bank} />}
                <InfoBox label="Status" value={selected.status} />
                {selected.assigned_user && <InfoBox label="Responsável" value={selected.assigned_user.name} />}
              </div>

              <div className="space-y-3 pt-2">
                {selected.messages.map(m => (
                  <div key={m.id} className={`rounded-lg p-3 text-sm ${m.direction === "out" ? "bg-blue-50 border-l-4 border-blue-400" : "bg-gray-50 border border-gray-100"}`}>
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span className="font-medium">{m.direction === "out" ? "Enviado" : (m.sender_name || m.sender_email)}</span>
                      <span>{new Date(m.received_at).toLocaleString()}</span>
                    </div>
                    <pre className="text-sm whitespace-pre-wrap text-gray-800 font-sans">{m.body_text || ""}</pre>
                    {m.attachments?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {m.attachments.map(att => (
                          <a key={att.id} href={api.downloadAttachment(m.id, att.id)} target="_blank" rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 bg-blue-50 px-2 py-0.5 rounded">
                            📎 {att.filename}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded p-2">
      <div className="text-gray-400 uppercase text-xs">{label}</div>
      <div className="font-medium text-gray-700 mt-0.5">{value}</div>
    </div>
  );
}
