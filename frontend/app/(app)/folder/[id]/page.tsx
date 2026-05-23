"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, Demand, DemandDetail, Folder } from "@/lib/api";
import { toast } from "@/lib/toast";

export default function FolderPage() {
  const params = useParams();
  const folderId = Number(params.id);

  const [folder, setFolder] = useState<Folder | null>(null);
  const [demands, setDemands] = useState<Demand[]>([]);
  const [selected, setSelected] = useState<DemandDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [otherFolders, setOtherFolders] = useState<Folder[]>([]);

  async function load() {
    setLoading(true);
    try {
      const [all, data] = await Promise.all([
        api.listFolders(),
        api.listFolderDemands(folderId),
      ]);
      const current = all.find(f => f.id === folderId) ?? null;
      setFolder(current);
      setOtherFolders(all.filter(f => f.id !== folderId));
      setDemands(data);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  useEffect(() => { load(); }, [folderId]);

  async function openDemand(d: Demand) {
    try {
      const detail = await api.getDemand(d.id);
      setSelected(detail);
    } catch (e: any) { setError(e.message); }
  }

  async function removeFromFolder(d: Demand) {
    try {
      await api.unarchiveDemand(d.id);
      setDemands(prev => prev.filter(x => x.id !== d.id));
      if (selected?.id === d.id) setSelected(null);
      toast("Demanda movida para a caixa de entrada.", "info");
      window.dispatchEvent(new Event("folderchange"));
    } catch (e: any) { toast(e.message, "error"); }
  }

  async function moveToFolder(d: Demand, targetFolderId: number) {
    try {
      await api.archiveDemand(d.id, targetFolderId);
      setDemands(prev => prev.filter(x => x.id !== d.id));
      if (selected?.id === d.id) setSelected(null);
      toast("Demanda movida para outra pasta.", "info");
      window.dispatchEvent(new Event("folderchange"));
    } catch (e: any) { toast(e.message, "error"); }
  }

  async function archiveDead(d: Demand) {
    if (!confirm("Enviar para o Arquivo Morto? O caso será marcado como finalizado.")) return;
    try {
      await api.closeArchive(d.id);
      setDemands(prev => prev.filter(x => x.id !== d.id));
      if (selected?.id === d.id) setSelected(null);
      toast("Caso enviado para o Arquivo Morto.", "success");
      window.dispatchEvent(new Event("archivechange"));
      window.dispatchEvent(new Event("folderchange"));
    } catch (e: any) { toast(e.message, "error"); }
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <span>📁</span>
          <span>{folder?.name ?? "Pasta"}</span>
        </h1>
        <span className="text-sm text-gray-500">{demands.length} demanda{demands.length !== 1 ? "s" : ""}</span>
      </div>

      {error && <div className="card p-3 mb-3 text-sm text-red-700 bg-red-50">{error}</div>}

      <div className="grid grid-cols-12 gap-4 h-[calc(100vh-160px)]">
        {/* Lista */}
        <div className="col-span-5 card overflow-y-auto">
          {loading && <div className="p-4 text-sm text-gray-400">Carregando...</div>}
          {!loading && demands.length === 0 && (
            <div className="p-6 text-sm text-gray-400">Esta pasta está vazia.</div>
          )}
          <div className="divide-y divide-gray-100">
            {demands.map(d => (
              <div
                key={d.id}
                onClick={() => openDemand(d)}
                className={`group flex cursor-pointer hover:bg-gray-50 ${selected?.id === d.id ? "bg-blue-50" : ""}`}
              >
                <div style={{ width: 4, flexShrink: 0, backgroundColor: d.email_account?.color ?? "#9ca3af" }} />
                <div className="flex-1 min-w-0 px-3 py-3">
                  <div className="flex justify-between items-start gap-2">
                    <div className="font-medium text-sm truncate">{d.sender_name || d.sender_email}</div>
                    <div className="text-xs text-gray-400 shrink-0">{new Date(d.last_message_at).toLocaleDateString()}</div>
                  </div>
                  <div className="text-xs text-gray-600 truncate mt-0.5">{d.subject || "(sem assunto)"}</div>
                  <div className="flex gap-1 mt-1.5 flex-wrap">
                    <span className="badge bg-gray-100 text-gray-600">{d.status}</span>
                    {d.assigned_user && <span className="badge bg-green-100 text-green-800">{d.assigned_user.name}</span>}
                  </div>
                </div>
                <button
                  className="opacity-0 group-hover:opacity-100 transition-opacity px-2 text-gray-400 hover:text-orange-600 self-center shrink-0 text-base"
                  title="Arquivo Morto"
                  onClick={async e => { e.stopPropagation(); await archiveDead(d); }}
                >⬇</button>
              </div>
            ))}
          </div>
        </div>

        {/* Detalhe */}
        <div className="col-span-7 card overflow-y-auto">
          {!selected ? (
            <div className="p-6 text-sm text-gray-500">Selecione uma demanda para ver os detalhes.</div>
          ) : (
            <div className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-semibold">{selected.subject || "(sem assunto)"}</h2>
                  <p className="text-sm text-gray-500 mt-0.5">De: {selected.sender_name || ""} &lt;{selected.sender_email}&gt;</p>
                </div>
                <div className="flex gap-2 flex-wrap justify-end">
                  <button
                    className="btn-secondary text-xs"
                    onClick={() => removeFromFolder(selected)}
                    title="Move para a caixa de entrada"
                  >↩ Remover da pasta</button>
                  <button
                    className="btn-danger text-xs"
                    onClick={() => archiveDead(selected)}
                    title="Envia para o Arquivo Morto"
                  >⬇ Arquivo Morto</button>
                </div>
              </div>

              {otherFolders.length > 0 && (
                <div>
                  <select
                    className="input text-sm w-52"
                    value=""
                    onChange={async e => {
                      const id = Number(e.target.value);
                      if (!id) return;
                      await moveToFolder(selected, id);
                    }}
                  >
                    <option value="">Mover para outra pasta...</option>
                    {otherFolders.map(f => <option key={f.id} value={f.id}>📁 {f.name}</option>)}
                  </select>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 text-sm pt-1">
                {selected.client_name && <Detail label="Cliente" value={selected.client_name} />}
                {selected.nup && <Detail label="NUP" value={selected.nup} />}
                {selected.bank && <Detail label="Banco" value={selected.bank} />}
                <Detail label="Status" value={selected.status} />
                {selected.assigned_user && <Detail label="Responsável" value={selected.assigned_user.name} />}
              </div>

              <div className="space-y-3 pt-2 border-t">
                {selected.messages.map(m => (
                  <div key={m.id} className={`rounded-lg p-3 text-sm ${m.direction === "out" ? "bg-blue-50 border-l-4 border-blue-400" : "bg-gray-50"}`}>
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>{m.direction === "out" ? "Enviado" : (m.sender_name || m.sender_email)}</span>
                      <span>{new Date(m.received_at).toLocaleString()}</span>
                    </div>
                    <pre className="text-sm whitespace-pre-wrap text-gray-800 font-sans">{m.body_text || ""}</pre>
                    {m.attachments?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {m.attachments.map(att => (
                          <a key={att.id} href={api.downloadAttachment(m.id, att.id)} target="_blank" rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
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

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-400 uppercase">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}
