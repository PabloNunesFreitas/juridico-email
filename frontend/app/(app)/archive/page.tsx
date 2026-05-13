"use client";
import { useEffect, useState } from "react";
import { api, Demand, Folder } from "@/lib/api";

export default function ArchivePage() {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<Folder | null>(null);
  const [demands, setDemands] = useState<Demand[]>([]);
  const [selectedDemand, setSelectedDemand] = useState<Demand | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadFolders() {
    try {
      const data = await api.listFolders();
      setFolders(data);
    } catch (e: any) { setError(e.message); }
  }

  async function openFolder(folder: Folder) {
    setSelectedFolder(folder);
    setSelectedDemand(null);
    setLoading(true);
    try {
      setDemands(await api.listFolderDemands(folder.id));
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  async function createFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      await api.createFolder(name);
      setNewFolderName("");
      await loadFolders();
    } catch (e: any) { setError(e.message); }
  }

  async function renameFolder() {
    if (!renaming || !renaming.name.trim()) return;
    try {
      await api.renameFolder(renaming.id, renaming.name.trim());
      setRenaming(null);
      await loadFolders();
      if (selectedFolder?.id === renaming.id) {
        setSelectedFolder(f => f ? { ...f, name: renaming.name.trim() } : f);
      }
    } catch (e: any) { setError(e.message); }
  }

  async function deleteFolder(folder: Folder) {
    if (!confirm(`Excluir pasta "${folder.name}"? As demandas voltarão para a caixa de entrada.`)) return;
    try {
      await api.deleteFolder(folder.id);
      if (selectedFolder?.id === folder.id) {
        setSelectedFolder(null);
        setDemands([]);
      }
      await loadFolders();
    } catch (e: any) { setError(e.message); }
  }

  async function unarchiveDemand(demand: Demand) {
    try {
      await api.unarchiveDemand(demand.id);
      setDemands(prev => prev.filter(d => d.id !== demand.id));
      if (selectedDemand?.id === demand.id) setSelectedDemand(null);
      await loadFolders();
    } catch (e: any) { setError(e.message); }
  }

  useEffect(() => { loadFolders(); }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Arquivo Morto</h1>
      {error && <div className="card p-3 mb-3 text-sm text-red-700 bg-red-50">{error}</div>}

      <div className="grid grid-cols-12 gap-4 h-[calc(100vh-140px)]">

        {/* Painel esquerdo — pastas */}
        <div className="col-span-3 card overflow-y-auto flex flex-col">
          <div className="p-3 border-b">
            <p className="text-xs uppercase text-gray-500 font-medium mb-2">Minhas pastas</p>
            <div className="flex gap-2">
              <input
                className="input flex-1 text-sm"
                placeholder="Nova pasta..."
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && createFolder()}
              />
              <button
                className="btn-primary text-sm px-3"
                onClick={createFolder}
                disabled={!newFolderName.trim()}
              >+</button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
            {folders.length === 0 && (
              <p className="p-4 text-sm text-gray-400">Nenhuma pasta criada ainda.</p>
            )}
            {folders.map(folder => (
              <div
                key={folder.id}
                className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer hover:bg-gray-50 ${selectedFolder?.id === folder.id ? "bg-blue-50" : ""}`}
                onClick={() => openFolder(folder)}
              >
                {renaming?.id === folder.id ? (
                  <input
                    className="input flex-1 text-sm py-0.5"
                    value={renaming.name}
                    autoFocus
                    onChange={e => setRenaming({ ...renaming, name: e.target.value })}
                    onKeyDown={e => { if (e.key === "Enter") renameFolder(); if (e.key === "Escape") setRenaming(null); }}
                    onBlur={renameFolder}
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <span className="text-gray-400 text-base">📁</span>
                    <span className="flex-1 text-sm font-medium truncate">{folder.name}</span>
                    <span className="text-xs text-gray-400 shrink-0">{folder.demand_count}</span>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 shrink-0" onClick={e => e.stopPropagation()}>
                      <button
                        className="text-gray-400 hover:text-blue-600 text-xs px-1"
                        title="Renomear"
                        onClick={e => { e.stopPropagation(); setRenaming({ id: folder.id, name: folder.name }); }}
                      >✏️</button>
                      <button
                        className="text-gray-400 hover:text-red-600 text-xs px-1"
                        title="Excluir"
                        onClick={e => { e.stopPropagation(); deleteFolder(folder); }}
                      >🗑️</button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Painel central — demandas da pasta */}
        <div className="col-span-4 card overflow-y-auto">
          {!selectedFolder ? (
            <div className="p-6 text-sm text-gray-400">Selecione uma pasta para ver as demandas.</div>
          ) : (
            <>
              <div className="p-3 border-b flex items-center justify-between">
                <span className="font-medium text-sm">📁 {selectedFolder.name}</span>
                <span className="text-xs text-gray-400">{demands.length} demanda{demands.length !== 1 ? "s" : ""}</span>
              </div>
              {loading && <div className="p-4 text-sm text-gray-400">Carregando...</div>}
              {!loading && demands.length === 0 && (
                <div className="p-4 text-sm text-gray-400">Pasta vazia.</div>
              )}
              <div className="divide-y divide-gray-100">
                {demands.map(d => (
                  <div
                    key={d.id}
                    onClick={() => setSelectedDemand(d)}
                    className={`flex cursor-pointer border-b border-gray-100 ${selectedDemand?.id === d.id ? "bg-blue-50" : ""}`}
                  >
                    <div style={{ width: 5, flexShrink: 0, backgroundColor: d.email_account?.color ?? "#e5e7eb" }} />
                    <div className="flex-1 min-w-0 px-3 py-3 hover:bg-gray-50">
                      <div className="flex justify-between items-start gap-2">
                        <div className="font-medium text-sm truncate">{d.sender_name || d.sender_email}</div>
                        <div className="text-xs text-gray-400 shrink-0">{new Date(d.last_message_at).toLocaleDateString()}</div>
                      </div>
                      <div className="text-xs text-gray-600 truncate mt-0.5">{d.subject || "(sem assunto)"}</div>
                      <div className="flex gap-1 mt-1.5 flex-wrap">
                        <span className="badge bg-gray-100 text-gray-600">{d.status}</span>
                        {d.bank && <span className="badge bg-blue-50 text-blue-700">{d.bank}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Painel direito — detalhe da demanda */}
        <div className="col-span-5 card overflow-y-auto">
          {!selectedDemand ? (
            <div className="p-6 text-sm text-gray-400">Selecione uma demanda para ver detalhes.</div>
          ) : (
            <div className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-semibold">{selectedDemand.subject || "(sem assunto)"}</h2>
                  <p className="text-sm text-gray-500 mt-0.5">De: {selectedDemand.sender_name || ""} &lt;{selectedDemand.sender_email}&gt;</p>
                </div>
                <button
                  className="btn-secondary text-xs shrink-0"
                  onClick={() => unarchiveDemand(selectedDemand)}
                  title="Retorna à caixa de entrada"
                >
                  ↩ Desarquivar
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2 text-sm">
                {selectedDemand.client_name && <Detail label="Cliente" value={selectedDemand.client_name} />}
                {selectedDemand.nup && <Detail label="NUP" value={selectedDemand.nup} />}
                {selectedDemand.bank && <Detail label="Banco" value={selectedDemand.bank} />}
                <Detail label="Status" value={selectedDemand.status} />
                {selectedDemand.assigned_user && <Detail label="Responsável" value={selectedDemand.assigned_user.name} />}
              </div>

              {/* Mover para outra pasta */}
              <div className="border-t pt-3">
                <p className="text-xs text-gray-500 mb-1">Mover para outra pasta:</p>
                <select
                  className="input w-full text-sm"
                  value=""
                  onChange={async (e) => {
                    const folderId = Number(e.target.value);
                    if (!folderId) return;
                    try {
                      await api.archiveDemand(selectedDemand.id, folderId);
                      setDemands(prev => prev.filter(d => d.id !== selectedDemand.id));
                      setSelectedDemand(null);
                      await loadFolders();
                    } catch (err: any) { setError(err.message); }
                  }}
                >
                  <option value="">Selecionar pasta...</option>
                  {folders.filter(f => f.id !== selectedFolder?.id).map(f => (
                    <option key={f.id} value={f.id}>{f.name}</option>
                  ))}
                </select>
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
