"use client";
import { useEffect, useState } from "react";
import { api, Demand, DemandDetail, EmailAccount, User, STATUSES, BANKS } from "@/lib/api";
import { ActionModal } from "@/components/ActionModal";

interface Props {
  source: "all" | "my" | "unassigned";
  title: string;
}

export function DemandView({ source, title }: Props) {
  const [demands, setDemands] = useState<Demand[]>([]);
  const [selected, setSelected] = useState<DemandDetail | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterAssignee, setFilterAssignee] = useState<string>(""); // "", "unassigned", "<userId>"
  const [filterAccount, setFilterAccount] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Modais de ação
  type ModalKind = "assume" | "unassign" | "assign";
  const [modal, setModal] = useState<ModalKind | null>(null);
  const [modalScope, setModalScope] = useState<"single" | "all">("single");
  const [modalAssignUserId, setModalAssignUserId] = useState<number | null>(null);

  // Resposta por e-mail
  const [replyText, setReplyText] = useState("");
  const [replySending, setReplySending] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [replySuccess, setReplySuccess] = useState(false);

  // Arquivo morto
  const [folders, setFolders] = useState<import("@/lib/api").Folder[]>([]);
  const [archiveOpen, setArchiveOpen] = useState(false);

  // Seleção múltipla
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkAssignUserId, setBulkAssignUserId] = useState<string>("");

  function toggleCheck(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    setCheckedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (checkedIds.size === demands.length) {
      setCheckedIds(new Set());
    } else {
      setCheckedIds(new Set(demands.map(d => d.id)));
    }
  }

  async function bulkAssume() {
    setBulkLoading(true);
    try {
      await Promise.all([...checkedIds].map(id => api.assumeDemand(id, false)));
      setCheckedIds(new Set());
      await loadList();
    } catch (e: any) { setError(e.message); }
    setBulkLoading(false);
  }

  async function bulkAssign(userId: number) {
    setBulkLoading(true);
    try {
      await Promise.all([...checkedIds].map(id => api.assignDemand(id, userId, false)));
      setCheckedIds(new Set());
      setBulkAssignUserId("");
      await loadList();
    } catch (e: any) { setError(e.message); }
    setBulkLoading(false);
  }

  async function bulkUnassign() {
    if (!confirm(`Remover responsável de ${checkedIds.size} demanda(s) selecionada(s)?`)) return;
    setBulkLoading(true);
    const ids = [...checkedIds];
    const errors: string[] = [];
    await Promise.all(ids.map(async id => {
      try { await api.unassignDemand(id, false, false); }
      catch (e: any) { errors.push(e.message); }
    }));
    setCheckedIds(new Set());
    await loadList();
    if (errors.length) setError(errors[0]);
    setBulkLoading(false);
  }

  async function loadList() {
    try {
      const params: Record<string, any> = { status: filterStatus || undefined, q: search.trim() || undefined };
      if (filterAssignee === "unassigned") params.unassigned = true;
      else if (filterAssignee) params.assigned_user_id = filterAssignee;
      if (filterAccount) params.email_account_id = filterAccount;
      let data: Demand[];
      if (source === "my") data = await api.myDemands(params);
      else if (source === "unassigned") data = await api.unassignedDemands(params);
      else data = await api.listDemands(params);
      setDemands(data);
    } catch (e: any) {
      setError(e.message);
    }
  }

  // Debounce: re-busca 350ms apos parar de digitar (ou imediato em filtros)
  useEffect(() => {
    const t = setTimeout(() => { loadList(); }, 350);
    return () => clearTimeout(t);
    /* eslint-disable-next-line */
  }, [source, filterStatus, filterAssignee, filterAccount, search]);

  // Auto-refresh: poll do sync/status; quando uma sync completa, recarrega a lista.
  // Tambem recarrega periodicamente como fallback.
  useEffect(() => {
    let alive = true;
    let lastFinishedAt: string | null = null;
    let lastReload = Date.now();
    async function tick() {
      if (!alive) return;
      try {
        const s = await api.syncStatus();
        const shouldReload =
          (s.finished_at && s.finished_at !== lastFinishedAt) ||
          (Date.now() - lastReload > 15_000);
        if (s.finished_at) lastFinishedAt = s.finished_at;
        if (shouldReload) {
          await loadList();
          lastReload = Date.now();
          // Atualiza tambem a demanda aberta (pega novas mensagens / mudancas de responsavel)
          if (selected) {
            try {
              const fresh = await api.getDemand(selected.id);
              setSelected(fresh);
            } catch { /* demanda pode ter sido atribuida a outro usuario */ }
          }
        }
      } catch {}
    }
    const id = setInterval(tick, 3000);
    return () => { alive = false; clearInterval(id); };
    /* eslint-disable-next-line */
  }, [source, filterStatus, filterAssignee, search, selected?.id]);
  useEffect(() => {
    api.me().then(setMe).catch(() => {});
    api.listUsers().then(setUsers).catch(() => {});
    api.listAccounts().then(setAccounts).catch(() => {});
    api.listFolders().then(setFolders).catch(() => {});
  }, []);

  async function open(d: Demand) {
    const detail = await api.getDemand(d.id);
    setSelected(detail);
    setReplyText("");
    setReplyError(null);
    setReplySuccess(false);
  }

  async function sendReply() {
    if (!selected || !replyText.trim()) return;
    setReplySending(true);
    setReplyError(null);
    setReplySuccess(false);
    try {
      const updated = await api.replyDemand(selected.id, replyText.trim());
      setSelected(updated);
      setReplyText("");
      setReplySuccess(true);
      setTimeout(() => setReplySuccess(false), 3000);
      await loadList();
    } catch (e: any) {
      setReplyError(e.message);
    }
    setReplySending(false);
  }

  async function refreshSelected() {
    if (!selected) return;
    setSelected(await api.getDemand(selected.id));
    await loadList();
  }

  const isAdmin = me?.role === "ADMIN";

  async function handleModalConfirm() {
    if (!selected) return;
    const bulk = modalScope === "all";
    try {
      if (modal === "assume") {
        await api.assumeDemand(selected.id, bulk);
      } else if (modal === "unassign") {
        await api.unassignDemand(selected.id, false, bulk);
      } else if (modal === "assign" && modalAssignUserId) {
        await api.assignDemand(selected.id, modalAssignUserId, bulk);
      }
      setModal(null);
      await refreshSelected();
    } catch (err: any) {
      setModal(null);
      setError(err.message);
    }
  }

  const assignTargetName = modalAssignUserId
    ? users.find(u => u.id === modalAssignUserId)?.name || "usuário"
    : "";

  return (
    <div>
      {/* Modal: Assumir demanda */}
      {modal === "assume" && selected && (
        <ActionModal
          title="Assumir demanda"
          subtitle={`De: ${selected.sender_email}`}
          options={[
            { value: "single", label: "Somente esta demanda" },
            {
              value: "all",
              label: "Todas as demandas deste remetente",
              description: "Novos e-mails deste endereço serão automaticamente atribuídos a você.",
            },
          ]}
          selected={modalScope}
          onSelect={(v) => setModalScope(v as "single" | "all")}
          confirmLabel="Assumir"
          onConfirm={handleModalConfirm}
          onCancel={() => setModal(null)}
        />
      )}

      {/* Modal: Remover responsável */}
      {modal === "unassign" && selected && (
        <ActionModal
          title="Remover responsável"
          subtitle={`De: ${selected.sender_email}`}
          options={[
            { value: "single", label: "Somente esta demanda" },
            {
              value: "all",
              label: "Todas as demandas deste remetente",
              description: "Remove o responsável de todas as demandas deste endereço de e-mail.",
            },
          ]}
          selected={modalScope}
          onSelect={(v) => setModalScope(v as "single" | "all")}
          confirmLabel="Remover"
          confirmClassName="btn-danger"
          onConfirm={handleModalConfirm}
          onCancel={() => setModal(null)}
        />
      )}

      {/* Modal: Atribuir a usuário */}
      {modal === "assign" && selected && (
        <ActionModal
          title={`Atribuir a ${assignTargetName}`}
          subtitle={`De: ${selected.sender_email}`}
          options={[
            { value: "single", label: "Somente esta demanda" },
            {
              value: "all",
              label: "Todas as demandas deste remetente",
              description: `Novos e-mails deste endereço serão automaticamente atribuídos a ${assignTargetName}.`,
            },
          ]}
          selected={modalScope}
          onSelect={(v) => setModalScope(v as "single" | "all")}
          confirmLabel="Atribuir"
          onConfirm={handleModalConfirm}
          onCancel={() => setModal(null)}
        />
      )}

      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h1 className="text-2xl font-bold">{title}</h1>
        <div className="flex gap-2 items-center">
          <div className="relative">
            <input
              className="input w-72 pr-8"
              placeholder="Buscar por remetente, assunto, NUP, corpo..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700 text-sm"
                aria-label="limpar busca"
              >×</button>
            )}
          </div>
          <select className="input w-56" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">Todos os status</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          {isAdmin && source === "all" && (
            <select className="input w-52" value={filterAssignee} onChange={(e) => setFilterAssignee(e.target.value)}>
              <option value="">Todos responsáveis</option>
              <option value="unassigned">— Sem responsável —</option>
              {users.filter(u => u.active).map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
          )}
          <span className="text-xs text-gray-500 whitespace-nowrap">{demands.length} resultados</span>
        </div>
      </div>
      {error && <div className="card p-3 mb-3 text-sm text-red-700 bg-red-50">{error}</div>}

      {/* Filtro por conta — chips coloridos */}
      {accounts.length > 1 && (
        <div className="flex gap-2 mb-3 flex-wrap items-center">
          <span className="text-xs text-gray-500">Conta:</span>
          <button
            onClick={() => setFilterAccount(null)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${filterAccount === null ? "bg-gray-800 text-white border-gray-800" : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"}`}
          >
            Todas
          </button>
          {accounts.map((acc) => (
            <button
              key={acc.id}
              onClick={() => setFilterAccount(filterAccount === acc.id ? null : acc.id)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${filterAccount === acc.id ? "text-white border-transparent" : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"}`}
              style={filterAccount === acc.id ? { backgroundColor: acc.color, borderColor: acc.color } : { borderBottomColor: acc.color, borderBottomWidth: 3 }}
              title={acc.email_address}
            >
              {acc.email_address}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-12 gap-4 h-[calc(100vh-160px)]">
        <div className="col-span-4 card overflow-y-auto flex flex-col">
          {/* Barra de seleção múltipla */}
          {checkedIds.size > 0 && (
            <div className="sticky top-0 z-10 bg-blue-600 text-white px-3 py-2 flex items-center gap-2 flex-wrap text-sm">
              <span className="font-medium">{checkedIds.size} selecionada{checkedIds.size > 1 ? "s" : ""}</span>
              <button
                className="bg-white text-blue-700 px-2 py-0.5 rounded text-xs font-medium hover:bg-blue-50 disabled:opacity-50"
                onClick={bulkAssume}
                disabled={bulkLoading}
              >
                Assumir
              </button>
              {isAdmin && (
                <>
                  <select
                    className="text-gray-800 text-xs px-2 py-0.5 rounded border-0 disabled:opacity-50"
                    value={bulkAssignUserId}
                    disabled={bulkLoading}
                    onChange={(e) => { if (e.target.value) { setBulkAssignUserId(e.target.value); bulkAssign(Number(e.target.value)); } }}
                  >
                    <option value="">Atribuir a...</option>
                    {users.filter(u => u.active).map(u => (
                      <option key={u.id} value={u.id}>{u.name}</option>
                    ))}
                  </select>
                  <button
                    className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-xs font-medium hover:bg-red-200 disabled:opacity-50"
                    onClick={bulkUnassign}
                    disabled={bulkLoading}
                  >
                    Remover responsável
                  </button>
                </>
              )}
              <button
                className="ml-auto text-blue-200 hover:text-white text-xs"
                onClick={() => setCheckedIds(new Set())}
              >
                Cancelar
              </button>
            </div>
          )}

          {/* Cabeçalho da lista com "selecionar todos" */}
          {demands.length > 0 && (
            <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
              <input
                type="checkbox"
                className="accent-blue-600"
                checked={checkedIds.size === demands.length && demands.length > 0}
                ref={el => { if (el) el.indeterminate = checkedIds.size > 0 && checkedIds.size < demands.length; }}
                onChange={toggleAll}
              />
              <span className="text-xs text-gray-400">Selecionar todos</span>
            </div>
          )}

          <div className="flex-1 overflow-y-auto">
            {demands.length === 0 && <div className="p-4 text-sm text-gray-500">Nenhuma demanda.</div>}
            {demands.map((d) => (
              <div
                key={d.id}
                onClick={() => open(d)}
                className={`flex cursor-pointer border-b border-gray-100 ${selected?.id === d.id ? "bg-blue-50" : ""} ${checkedIds.has(d.id) ? "bg-blue-50" : ""}`}
              >
                {/* Barra colorida — elemento real, não CSS trick */}
                <div style={{ width: 5, flexShrink: 0, backgroundColor: d.email_account?.color ?? "#e5e7eb" }} />

                <div className="flex-1 min-w-0 px-3 py-3 hover:bg-gray-50">
                  <div className="flex justify-between items-start gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <input
                        type="checkbox"
                        className="accent-blue-600 shrink-0"
                        checked={checkedIds.has(d.id)}
                        onClick={(e) => toggleCheck(d.id, e)}
                        onChange={() => {}}
                      />
                      <div className="font-medium text-sm truncate">{d.sender_name || d.sender_email}</div>
                    </div>
                    <div className="text-xs text-gray-500 shrink-0">{new Date(d.last_message_at).toLocaleDateString()}</div>
                  </div>
                  <div className="text-xs text-gray-700 truncate mt-0.5 pl-6">{d.subject || "(sem assunto)"}</div>
                  <div className="flex gap-1 mt-1.5 flex-wrap items-center pl-6">
                    <span className="badge bg-gray-100 text-gray-700">{d.status}</span>
                    {d.assigned_user ? (
                      <span className="badge bg-green-100 text-green-800">{d.assigned_user.name}</span>
                    ) : (
                      <span className="badge bg-amber-100 text-amber-800">Sem responsável</span>
                    )}
                    {d.email_account && accounts.length > 1 && (
                      <span
                        className="text-xs px-1.5 py-0.5 rounded font-medium ml-auto"
                        style={{ backgroundColor: d.email_account.color + "22", color: d.email_account.color }}
                      >
                        {d.email_account.email_address.split("@")[0]}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="col-span-5 card overflow-y-auto">
          {!selected ? (
            <div className="p-6 text-sm text-gray-500">Selecione uma demanda para ver detalhes.</div>
          ) : (
            <div className="p-4">
              <h2 className="text-lg font-semibold">{selected.subject || "(sem assunto)"}</h2>
              <div className="text-sm text-gray-600 mt-1">De: {selected.sender_name || ""} &lt;{selected.sender_email}&gt;</div>
              <div className="flex gap-2 mt-3 flex-wrap">
                {!selected.assigned_user && (
                  <button
                    className="btn-primary"
                    onClick={() => { setModalScope("single"); setModal("assume"); }}
                  >
                    Assumir demanda
                  </button>
                )}
                {isAdmin && (
                  <select className="input w-56" value=""
                    onChange={(e) => {
                      const newUserId = Number(e.target.value);
                      if (!newUserId) return;
                      setModalAssignUserId(newUserId);
                      setModalScope("single");
                      setModal("assign");
                    }}>
                    <option value="">Atribuir a...</option>
                    {users.filter(u => u.active).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </select>
                )}
                {isAdmin && selected.assigned_user && (
                  <button
                    className="btn-secondary"
                    onClick={() => { setModalScope("single"); setModal("unassign"); }}
                    title="Volta a demanda para 'Não atribuídas'"
                  >
                    Remover responsável
                  </button>
                )}
                <select className="input w-60" value={selected.status}
                  onChange={async (e) => { await api.changeStatus(selected.id, e.target.value); await refreshSelected(); }}>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>

                {/* Arquivar */}
                {selected.folder_id ? (
                  <button
                    className="btn-secondary text-xs"
                    onClick={async () => { await api.unarchiveDemand(selected.id); await refreshSelected(); await loadList(); }}
                  >↩ Desarquivar</button>
                ) : (
                  <div className="relative">
                    <button
                      className="btn-secondary text-xs"
                      onClick={() => { setArchiveOpen(v => !v); }}
                    >📁 Arquivar</button>
                    {archiveOpen && (
                      <div className="absolute right-0 top-full mt-1 bg-white border rounded shadow-lg z-20 w-52 py-1">
                        {folders.length === 0 && (
                          <p className="px-3 py-2 text-xs text-gray-400">Crie pastas em Arquivo Morto primeiro.</p>
                        )}
                        {folders.map(f => (
                          <button
                            key={f.id}
                            className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50"
                            onClick={async () => {
                              setArchiveOpen(false);
                              await api.archiveDemand(selected.id, f.id);
                              await loadList();
                              setSelected(null);
                            }}
                          >📁 {f.name}</button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="mt-5 space-y-3">
                {selected.messages.map((m) => (
                  <div
                    key={m.id}
                    className={`card p-3 ${m.direction === "out" ? "border-l-4 border-blue-400 bg-blue-50" : ""}`}
                  >
                    <div className="flex justify-between text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        {m.direction === "out" && (
                          <span className="text-blue-600 font-medium">Enviado</span>
                        )}
                        {m.sender_name || m.sender_email}
                      </span>
                      <span>{new Date(m.received_at).toLocaleString()}</span>
                    </div>
                    <div className="text-sm font-medium mt-1">{m.subject}</div>
                    <pre className="text-sm whitespace-pre-wrap mt-2 text-gray-800 font-sans">{m.body_text || ""}</pre>
                    {m.has_attachments && <div className="text-xs text-blue-600 mt-2">📎 Possui anexos</div>}
                  </div>
                ))}
              </div>

              {/* Caixa de resposta */}
              <div className="mt-6 border-t pt-4">
                <div className="text-xs text-gray-500 mb-1 uppercase font-medium">
                  Responder para: <span className="text-gray-700 normal-case font-normal">{selected.sender_email}</span>
                </div>
                <textarea
                  className="input w-full mt-1 text-sm"
                  rows={5}
                  placeholder="Digite sua resposta..."
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  disabled={replySending}
                />
                {replyError && (
                  <div className="text-xs text-red-600 mt-1">{replyError}</div>
                )}
                {replySuccess && (
                  <div className="text-xs text-green-600 mt-1">E-mail enviado com sucesso!</div>
                )}
                <div className="flex justify-end mt-2">
                  <button
                    className="btn-primary disabled:opacity-50"
                    onClick={sendReply}
                    disabled={replySending || !replyText.trim()}
                  >
                    {replySending ? "Enviando..." : "Enviar resposta"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="col-span-3 card overflow-y-auto">
          {!selected ? (
            <div className="p-4 text-sm text-gray-500">—</div>
          ) : (
            <div className="p-4 space-y-3 text-sm">
              <h3 className="font-semibold text-base mb-2">Dados da demanda</h3>
              <Field label="Responsável" value={selected.assigned_user?.name || "—"} />
              <Field label="Banco">
                <select className="input mt-1" value={selected.bank ?? ""}
                  onChange={async (e) => { await api.updateDemand(selected.id, { bank: e.target.value || undefined }); await refreshSelected(); }}>
                  <option value="">—</option>
                  {BANKS.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </Field>
              <Field label="Status" value={selected.status} />
              <Field label="Cliente">
                <input className="input mt-1" defaultValue={selected.client_name || ""}
                  onBlur={async (e) => { if (e.target.value !== (selected.client_name || "")) { await api.updateDemand(selected.id, { client_name: e.target.value }); await refreshSelected(); } }} />
              </Field>
              <Field label="NUP">
                <input className="input mt-1" defaultValue={selected.nup || ""}
                  onBlur={async (e) => { if (e.target.value !== (selected.nup || "")) { await api.updateDemand(selected.id, { nup: e.target.value }); await refreshSelected(); } }} />
              </Field>
              <DemandLogs demandId={selected.id} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, children }: { label: string; value?: string; children?: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase text-gray-500">{label}</div>
      {children ?? <div className="mt-0.5">{value}</div>}
    </div>
  );
}

function DemandLogs({ demandId }: { demandId: number }) {
  const [logs, setLogs] = useState<any[]>([]);
  useEffect(() => { api.demandLogs(demandId).then(setLogs).catch(() => setLogs([])); }, [demandId]);
  return (
    <div className="pt-3 border-t mt-3">
      <div className="text-xs uppercase text-gray-500 mb-2">Histórico</div>
      <div className="space-y-1.5 max-h-64 overflow-y-auto">
        {logs.map((l) => (
          <div key={l.id} className="text-xs">
            <span className="text-gray-500">{new Date(l.created_at).toLocaleString()}</span> — <span className="font-medium">{l.event_type}</span>
            {l.description && <div className="text-gray-700">{l.description}</div>}
          </div>
        ))}
        {logs.length === 0 && <div className="text-xs text-gray-400">Sem histórico.</div>}
      </div>
    </div>
  );
}
