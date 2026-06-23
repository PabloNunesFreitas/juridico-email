"use client";
import { useEffect, useRef, useState } from "react";
import { api, Comment, Demand, DemandDetail, EmailAccount, User, STATUSES, BANKS } from "@/lib/api";
import { ActionModal } from "@/components/ActionModal";
import { toast } from "@/lib/toast";

interface Props {
  source: "all" | "my" | "unassigned" | "shared" | "folder";
  title: string;
  folderId?: number;
}

export function DemandView({ source, title, folderId }: Props) {
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
  const [replyCc, setReplyCc] = useState("");
  const [replyTo, setReplyTo] = useState<string[]>([]);
  const [replyToInput, setReplyToInput] = useState("");
  const [replySending, setReplySending] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [replySuccess, setReplySuccess] = useState(false);

  // Compose novo e-mail
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeTo, setComposeTo] = useState<string[]>([]);
  const [composeToInput, setComposeToInput] = useState("");
  const [composeCc, setComposeCc] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeAccountId, setComposeAccountId] = useState<number | null>(null);
  const [composeSending, setComposeSending] = useState(false);
  const [composeError, setComposeError] = useState<string | null>(null);
  const [composeFiles, setComposeFiles] = useState<File[]>([]);
  const [replyFiles, setReplyFiles] = useState<File[]>([]);

  // Pastas (para mover)
  const [folders, setFolders] = useState<import("@/lib/api").Folder[]>([]);
  const [moveOpen, setMoveOpen] = useState(false);

  // Compartilhar
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUserId, setShareUserId] = useState("");
  const [shareNote, setShareNote] = useState("");

  // Comentários
  const [comments, setComments] = useState<Comment[]>([]);
  const [newComment, setNewComment] = useState("");
  const [commentSending, setCommentSending] = useState(false);
  const commentsEndRef = useRef<HTMLDivElement>(null);

  // @mention dropdown
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const commentInputRef = useRef<HTMLInputElement>(null);

  // Assumir demanda compartilhada
  const [assumingShared, setAssumingShared] = useState(false);
  const [dismissedAssume, setDismissedAssume] = useState<Set<number>>(new Set());

  // Menções pendentes (@menção não respondida)
  const [pendingMentionIds, setPendingMentionIds] = useState<Set<number>>(new Set());

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
    const results = await Promise.allSettled([...checkedIds].map(id => api.assumeDemand(id, false)));
    const failed = results.filter(r => r.status === "rejected");
    if (failed.length) setError(`${failed.length} demanda(s) falharam ao assumir`);
    setCheckedIds(new Set());
    await loadList();
    setBulkLoading(false);
  }

  async function bulkAssign(userId: number) {
    setBulkLoading(true);
    const results = await Promise.allSettled([...checkedIds].map(id => api.assignDemand(id, userId, false)));
    const failed = results.filter(r => r.status === "rejected");
    if (failed.length) setError(`${failed.length} demanda(s) falharam ao atribuir`);
    setCheckedIds(new Set());
    setBulkAssignUserId("");
    await loadList();
    setBulkLoading(false);
  }

  async function bulkUnassign() {
    if (!confirm(`Remover responsável de ${checkedIds.size} demanda(s) selecionada(s)?`)) return;
    setBulkLoading(true);
    const results = await Promise.allSettled([...checkedIds].map(id => api.unassignDemand(id, false, false)));
    const failed = results.filter(r => r.status === "rejected");
    setCheckedIds(new Set());
    await loadList();
    if (failed.length) setError(`${failed.length} demanda(s) falharam ao remover responsável`);
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
      else if (source === "shared") data = await api.sharedDemands();
      else if (source === "folder" && folderId) data = await api.listFolderDemands(folderId);
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
    function loadPending() {
      api.pendingMentions().then(ids => setPendingMentionIds(new Set(ids))).catch(() => {});
    }
    loadPending();
    const t = setInterval(loadPending, 30_000);
    return () => clearInterval(t);
  }, []);

  async function closeArchiveDemand(d: Demand) {
    try {
      await api.closeArchive(d.id);
      setDemands(prev => prev.filter(x => x.id !== d.id));
      if (selected?.id === d.id) setSelected(null);
      toast("Caso enviado para o Arquivo Morto.", "success");
      window.dispatchEvent(new Event("archivechange"));
    } catch (e: any) { toast(e.message, "error"); }
  }

  async function open(d: Demand) {
    const detail = await api.getDemand(d.id);
    setSelected(detail);
    setReplyText("");
    setReplyTo([detail.sender_email]);
    setReplyToInput("");
    setReplyCc("");
    setReplyError(null);
    setReplySuccess(false);
    setShareOpen(false);
    setMoveOpen(false);
    api.listComments(d.id).then(setComments).catch(() => setComments([]));
  }

  async function sendComment() {
    if (!selected || !newComment.trim()) return;
    setCommentSending(true);
    try {
      const mentionedIds = extractMentionIds(newComment, users);
      const c = await api.addComment(selected.id, newComment.trim(), mentionedIds);
      setComments(prev => [...prev, c]);
      setNewComment("");
      setMentionQuery(null);
      setTimeout(() => commentsEndRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
      api.pendingMentions().then(ids => setPendingMentionIds(new Set(ids))).catch(() => {});
    } catch (e: any) { toast(e.message, "error"); }
    setCommentSending(false);
  }

  function extractMentionIds(text: string, userList: User[]): number[] {
    const sorted = [...userList].sort((a, b) => b.name.length - a.name.length);
    const ids: number[] = [];
    let i = 0;
    while (i < text.length) {
      const atIdx = text.indexOf("@", i);
      if (atIdx === -1) break;
      const after = text.slice(atIdx + 1);
      const found = sorted.find(u => after.toLowerCase().startsWith(u.name.toLowerCase()));
      if (found && !ids.includes(found.id)) ids.push(found.id);
      i = atIdx + 1;
    }
    return ids;
  }

  function handleCommentChange(value: string) {
    setNewComment(value);
    const atIdx = value.lastIndexOf("@");
    if (atIdx !== -1) {
      const after = value.slice(atIdx + 1);
      const hasMatch = users.some(u => u.id !== me?.id && u.name.toLowerCase().startsWith(after.toLowerCase()));
      if (hasMatch || after.length === 0) {
        setMentionQuery(after.toLowerCase());
        setMentionIndex(0);
        return;
      }
    }
    setMentionQuery(null);
  }

  function mentionSuggestions() {
    if (mentionQuery === null) return [];
    return users.filter(u => u.id !== me?.id && u.name.toLowerCase().startsWith(mentionQuery));
  }

  function renderMentions(content: string) {
    const sorted = [...users].sort((a, b) => b.name.length - a.name.length);
    const result: React.ReactNode[] = [];
    let remaining = content;
    let key = 0;
    while (remaining.length > 0) {
      const atIdx = remaining.indexOf("@");
      if (atIdx === -1) { result.push(remaining); break; }
      if (atIdx > 0) result.push(remaining.slice(0, atIdx));
      const after = remaining.slice(atIdx + 1);
      const matched = sorted.find(u => after.toLowerCase().startsWith(u.name.toLowerCase()));
      if (matched) {
        result.push(<span key={key++} className="text-blue-600 font-medium">@{matched.name}</span>);
        remaining = remaining.slice(atIdx + 1 + matched.name.length);
      } else {
        const end = after.search(/\s|$/) + 1;
        result.push(remaining.slice(atIdx, atIdx + end));
        remaining = remaining.slice(atIdx + end);
      }
    }
    return result;
  }

  function pickMention(u: User) {
    const atIdx = newComment.lastIndexOf("@");
    setNewComment(newComment.slice(0, atIdx) + `@${u.name} `);
    setMentionQuery(null);
    commentInputRef.current?.focus();
  }

  async function assumeSharedDemand() {
    if (!selected) return;
    setAssumingShared(true);
    try {
      const updated = await api.joinDemand(selected.id);
      setSelected(prev => prev ? { ...prev, ...updated, messages: prev.messages } : prev);
      await loadList();
      toast("Você entrou como co-responsável!", "success");
    } catch (e: any) { toast(e.message, "error"); }
    setAssumingShared(false);
  }

  async function sendReply() {
    if (!selected || !replyText.trim()) return;
    if (replyTo.length === 0) { setReplyError("Informe ao menos um destinatário."); return; }
    setReplySending(true);
    setReplyError(null);
    setReplySuccess(false);
    try {
      const ccList = replyCc.split(",").map(s => s.trim()).filter(Boolean);
      const updated = await api.replyDemand(selected.id, replyText.trim(), ccList, replyTo, replyFiles);
      setSelected(updated);
      setReplyText("");
      setReplyCc("");
      setReplyFiles([]);
      setReplySuccess(true);
      setTimeout(() => setReplySuccess(false), 3000);
      await loadList();
    } catch (e: any) {
      setReplyError(e.message);
    }
    setReplySending(false);
  }

  async function sendCompose() {
    if (composeTo.length === 0 || !composeSubject.trim() || !composeBody.trim()) {
      setComposeError("Preencha: Para, Assunto e corpo do e-mail.");
      return;
    }
    setComposeSending(true);
    setComposeError(null);
    try {
      const ccList = composeCc.split(",").map(s => s.trim()).filter(Boolean);
      await api.composeEmail({ to_emails: composeTo, cc: ccList, subject: composeSubject.trim(), body_text: composeBody.trim(), account_id: composeAccountId ?? undefined, files: composeFiles });
      setComposeOpen(false);
      setComposeTo([]);
      setComposeToInput("");
      setComposeCc("");
      setComposeSubject("");
      setComposeBody("");
      setComposeAccountId(null);
      setComposeFiles([]);
      toast("E-mail enviado!", "success");
    } catch (e: any) {
      setComposeError(e.message);
    }
    setComposeSending(false);
  }

  async function refreshSelected() {
    if (!selected) return;
    setSelected(await api.getDemand(selected.id));
    await loadList();
  }

  async function handleShare() {
    if (!selected || !shareUserId) return;
    try {
      await api.shareDemand(selected.id, Number(shareUserId), shareNote || undefined);
      setShareOpen(false);
      setShareUserId("");
      setShareNote("");
      toast("Demanda compartilhada com sucesso!", "success");
    } catch (e: any) {
      toast(e.message, "error");
    }
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
      if (modal === "assume") toast("Demanda assumida!", "success");
      else if (modal === "unassign") toast("Responsável removido.", "info");
      else if (modal === "assign") toast(`Demanda atribuída a ${assignTargetName}.`, "success");
    } catch (err: any) {
      setModal(null);
      setError(err.message);
      toast(err.message, "error");
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

      {/* Modal Novo E-mail */}
      {composeOpen && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Novo E-mail</h2>
            {/* Conta de envio */}
            {accounts.length > 1 && (
              <div className="mb-3">
                <label className="text-xs text-gray-500 uppercase font-medium">Enviar de:</label>
                <select
                  className="input text-sm mt-1 w-full"
                  value={composeAccountId ?? ""}
                  onChange={e => setComposeAccountId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">Conta padrão</option>
                  {accounts.map(acc => (
                    <option key={acc.id} value={acc.id}>
                      {acc.email_address} ({acc.provider})
                    </option>
                  ))}
                </select>
              </div>
            )}
            {/* Para */}
            <div className="mb-3">
              <label className="text-xs text-gray-500 uppercase font-medium">Para:</label>
              <div className="mt-1 flex flex-wrap gap-1 items-center border rounded px-2 py-1.5 bg-white focus-within:ring-1 focus-within:ring-blue-400">
                {composeTo.map(email => (
                  <span key={email} className="inline-flex items-center gap-1 bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded-full">
                    {email}
                    <button type="button" className="text-blue-500 hover:text-red-500" onClick={() => setComposeTo(prev => prev.filter(e => e !== email))}>×</button>
                  </span>
                ))}
                <input
                  className="flex-1 min-w-24 text-sm outline-none"
                  placeholder="destinatario@exemplo.com"
                  value={composeToInput}
                  onChange={e => setComposeToInput(e.target.value)}
                  onKeyDown={e => {
                    if ((e.key === "Enter" || e.key === ",") && composeToInput.trim()) {
                      e.preventDefault();
                      const email = composeToInput.trim().replace(/,$/, "");
                      if (email && !composeTo.includes(email)) setComposeTo(prev => [...prev, email]);
                      setComposeToInput("");
                    }
                    if (e.key === "Backspace" && !composeToInput && composeTo.length > 0) setComposeTo(prev => prev.slice(0, -1));
                  }}
                  onBlur={() => {
                    const email = composeToInput.trim().replace(/,$/, "");
                    if (email && !composeTo.includes(email)) setComposeTo(prev => [...prev, email]);
                    setComposeToInput("");
                  }}
                />
              </div>
            </div>
            {/* CC */}
            <div className="mb-3">
              <label className="text-xs text-gray-500 uppercase font-medium">CC:</label>
              <input className="input text-sm mt-1 w-full" placeholder="email1@exemplo.com, email2@exemplo.com" value={composeCc} onChange={e => setComposeCc(e.target.value)} />
            </div>
            {/* Assunto */}
            <div className="mb-3">
              <label className="text-xs text-gray-500 uppercase font-medium">Assunto:</label>
              <input className="input text-sm mt-1 w-full" placeholder="Assunto do e-mail" value={composeSubject} onChange={e => setComposeSubject(e.target.value)} />
            </div>
            {/* Corpo */}
            <div className="mb-3">
              <label className="text-xs text-gray-500 uppercase font-medium">Mensagem:</label>
              <textarea className="input text-sm mt-1 w-full" rows={6} placeholder="Digite a mensagem..." value={composeBody} onChange={e => setComposeBody(e.target.value)} />
            </div>
            {/* Anexos */}
            <div className="mb-3">
              <label className="text-xs text-gray-500 uppercase font-medium">Anexos:</label>
              <input type="file" multiple className="mt-1 text-sm w-full" onChange={e => {
                const files = Array.from(e.target.files ?? []);
                const tooBig = files.filter(f => f.size > 10 * 1024 * 1024);
                if (tooBig.length) { toast(`Arquivo muito grande (máx 10MB): ${tooBig[0].name}`, "error"); return; }
                setComposeFiles(files);
              }} />
              {composeFiles.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {composeFiles.map((f, i) => (
                    <span key={i} className="inline-flex items-center gap-1 bg-gray-100 text-gray-700 text-xs px-2 py-0.5 rounded-full">
                      📎 {f.name}
                      <button type="button" onClick={() => setComposeFiles(prev => prev.filter((_, j) => j !== i))} className="text-gray-400 hover:text-red-500">×</button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            {composeError && <div className="text-xs text-red-600 mb-2">{composeError}</div>}
            <div className="flex justify-end gap-2">
              <button className="btn-secondary" onClick={() => { setComposeOpen(false); setComposeError(null); setComposeFiles([]); }}>Cancelar</button>
              <button className="btn-primary disabled:opacity-50" disabled={composeSending} onClick={sendCompose}>
                {composeSending ? "Enviando..." : "Enviar"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
        <h1 className="text-xl md:text-2xl font-bold">{title}</h1>
        <button className="btn-secondary text-xs whitespace-nowrap" onClick={() => setComposeOpen(true)}>✉ Novo E-mail</button>
      </div>
      <div className="flex gap-2 items-center mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[160px]">
          <input
            className="input w-full pr-8"
            placeholder="Buscar por remetente, assunto, NUP..."
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
        <select className="input flex-1 min-w-[130px] md:w-56" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">Todos os status</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {isAdmin && source === "all" && (
          <select className="input flex-1 min-w-[130px] md:w-52" value={filterAssignee} onChange={(e) => setFilterAssignee(e.target.value)}>
            <option value="">Todos responsáveis</option>
            <option value="unassigned">— Sem responsável —</option>
            {users.filter(u => u.active).map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        )}
        <span className="text-xs text-gray-500 whitespace-nowrap">{demands.length} resultados</span>
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

      <div className="grid grid-cols-12 gap-3 md:gap-4 md:h-[calc(100vh-160px)]">
        <div className={`col-span-12 md:col-span-4 card overflow-y-auto flex flex-col ${selected ? "hidden md:flex" : "flex"}`}>
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
                className={`group flex cursor-pointer border-b border-gray-100 ${selected?.id === d.id ? "bg-blue-50" : ""} ${checkedIds.has(d.id) ? "bg-blue-50" : ""}`}
              >
                {/* Barra colorida — elemento real, não CSS trick */}
                <div style={{ width: 5, flexShrink: 0, backgroundColor: d.email_account?.color ?? "#e5e7eb" }} />

                <div className="flex-1 min-w-0 px-3 py-3 hover:bg-gray-50" onClick={() => open(d)}>
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
                    {pendingMentionIds.has(d.id) && (
                      <span className="badge bg-yellow-400 text-gray-900 font-semibold" title="Você tem @menção não respondida">⏳ Responder</span>
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
                {/* Botão Arquivo Morto — visível ao passar o mouse */}
                <button
                  className="opacity-0 group-hover:opacity-100 transition-opacity px-2 text-gray-300 hover:text-orange-500 self-center shrink-0 text-lg"
                  title="Enviar para Arquivo Morto"
                  onClick={e => { e.stopPropagation(); closeArchiveDemand(d); }}
                >⬇</button>
              </div>
            ))}
          </div>
        </div>

        <div className={`col-span-12 md:col-span-5 card overflow-y-auto ${!selected ? "hidden md:block" : "block"}`}>
          {!selected ? (
            <div className="p-6 text-sm text-gray-500">Selecione uma demanda para ver detalhes.</div>
          ) : (
            <div className="p-4">
              <button
                className="md:hidden flex items-center gap-1 text-sm text-blue-600 mb-3 font-medium"
                onClick={() => setSelected(null)}
              >
                ← Voltar
              </button>
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

                {/* Compartilhar */}
                <div className="relative">
                  <button
                    className="btn-secondary text-xs"
                    onClick={() => { setShareOpen(v => !v); }}
                  >
                    ↗ Compartilhar
                  </button>
                  {shareOpen && (
                    <div className="absolute left-0 top-full mt-1 bg-white border rounded shadow-lg z-20 w-64 p-3 space-y-2">
                      <p className="text-xs font-medium text-gray-700">Compartilhar com:</p>
                      <select
                        className="input text-sm"
                        value={shareUserId}
                        onChange={e => setShareUserId(e.target.value)}
                      >
                        <option value="">Selecionar usuário...</option>
                        {users.filter(u => u.active && u.id !== me?.id).map(u => (
                          <option key={u.id} value={u.id}>{u.name}</option>
                        ))}
                      </select>
                      <input
                        className="input text-sm"
                        placeholder="Mensagem (opcional)"
                        value={shareNote}
                        onChange={e => setShareNote(e.target.value)}
                      />
                      <div className="flex gap-2 justify-end">
                        <button className="btn-secondary text-xs" onClick={() => setShareOpen(false)}>Cancelar</button>
                        <button
                          className="btn-primary text-xs"
                          disabled={!shareUserId}
                          onClick={handleShare}
                        >Compartilhar</button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Arquivo Morto */}
                <button
                  className="btn-secondary text-xs"
                  title="Encerrar o caso e enviar para o Arquivo Morto"
                  onClick={async () => {
                    if (!confirm("Encerrar este caso e enviar para o Arquivo Morto?")) return;
                    await closeArchiveDemand(selected);
                  }}
                >⬇ Arquivo Morto</button>

                {/* Mover para pasta */}
                {folders.length > 0 && (
                  <div className="relative">
                    <button
                      className="btn-secondary text-xs"
                      onClick={() => { setMoveOpen(v => !v); setShareOpen(false); }}
                    >📁 {selected.folder_id ? "Mover de pasta" : "Mover para pasta"}</button>
                    {moveOpen && (
                      <div className="absolute right-0 top-full mt-1 bg-white border rounded shadow-lg z-20 w-52 py-1">
                        {selected.folder_id && (
                          <button
                            className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-500"
                            onClick={async () => {
                              setMoveOpen(false);
                              await api.unarchiveDemand(selected.id);
                              await refreshSelected();
                              await loadList();
                            }}
                          >↩ Remover da pasta</button>
                        )}
                        {folders.filter(f => f.id !== selected.folder_id).map(f => (
                          <button
                            key={f.id}
                            className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50"
                            onClick={async () => {
                              setMoveOpen(false);
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

              {/* Banner trabalhar junto na demanda compartilhada */}
              {source === "shared" && !selected.co_assignees?.some(c => c.user.id === me?.id) && !dismissedAssume.has(selected.id) && (
                <div className="mt-4 flex items-center justify-between bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-amber-800">Deseja trabalhar junto nesta demanda?</p>
                    <p className="text-xs text-amber-600 mt-0.5">
                      {selected.assigned_user ? `Responsável: ${selected.assigned_user.name}` : "Sem responsável atribuído"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="px-3 py-1.5 text-sm font-medium bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50"
                      onClick={assumeSharedDemand}
                      disabled={assumingShared}
                    >
                      {assumingShared ? "..." : "Trabalhar junto"}
                    </button>
                    <button
                      className="px-3 py-1.5 text-sm font-medium bg-white border border-amber-300 text-amber-700 rounded hover:bg-amber-50"
                      onClick={() => setDismissedAssume(prev => new Set([...prev, selected.id]))}
                    >
                      Não
                    </button>
                  </div>
                </div>
              )}

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
                    {m.recipient_emails && (
                      <div className="text-xs text-gray-500 mt-0.5">Para: {m.recipient_emails}</div>
                    )}
                    <div className="text-sm font-medium mt-1">{m.subject}</div>
                    <pre className="text-sm whitespace-pre-wrap mt-2 text-gray-800 font-sans">{m.body_text || ""}</pre>
                    {m.attachments && m.attachments.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {m.attachments.map(att => (
                          <a
                            key={att.id}
                            href={api.downloadAttachment(m.id, att.id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 bg-blue-50 px-2 py-1 rounded mr-1"
                          >
                            📎 {att.filename}
                            {att.size ? <span className="text-gray-400">({Math.round(att.size / 1024)}KB)</span> : null}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Conversa interna */}
              <div className="mt-6 border-t pt-4">
                <div className="text-xs text-gray-500 uppercase font-medium mb-2">Conversa Interna</div>
                <div className="space-y-2 max-h-52 overflow-y-auto mb-3">
                  {comments.length === 0 && (
                    <p className="text-xs text-gray-400">Nenhum comentário ainda.</p>
                  )}
                  {comments.map(c => (
                    <div key={c.id} className="bg-gray-50 rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs font-semibold text-gray-700">{c.user_name}</span>
                        <span className="text-xs text-gray-400">{new Date(c.created_at).toLocaleString()}</span>
                      </div>
                      <p className="text-sm text-gray-800 whitespace-pre-wrap">
                        {renderMentions(c.content)}
                      </p>
                    </div>
                  ))}
                  <div ref={commentsEndRef} />
                </div>
                <div className="relative flex gap-2">
                  {mentionQuery !== null && mentionSuggestions().length > 0 && (
                    <div className="absolute bottom-full left-0 mb-1 bg-white border rounded shadow-lg z-30 w-48 max-h-40 overflow-y-auto">
                      {mentionSuggestions().map((u, i) => (
                        <button
                          key={u.id}
                          className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 ${i === mentionIndex ? "bg-blue-50" : ""}`}
                          onMouseDown={(e) => { e.preventDefault(); pickMention(u); }}
                        >
                          <span className="font-medium text-blue-600">@</span>{u.name}
                        </button>
                      ))}
                    </div>
                  )}
                  <input
                    ref={commentInputRef}
                    className="input flex-1 text-sm"
                    placeholder="Comentário interno... (@usuário para mencionar)"
                    value={newComment}
                    onChange={e => handleCommentChange(e.target.value)}
                    onKeyDown={e => {
                      if (mentionQuery !== null && mentionSuggestions().length > 0) {
                        if (e.key === "ArrowDown") { e.preventDefault(); setMentionIndex(i => Math.min(i + 1, mentionSuggestions().length - 1)); return; }
                        if (e.key === "ArrowUp") { e.preventDefault(); setMentionIndex(i => Math.max(i - 1, 0)); return; }
                        if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pickMention(mentionSuggestions()[mentionIndex]); return; }
                        if (e.key === "Escape") { setMentionQuery(null); return; }
                      }
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendComment(); }
                    }}
                    disabled={commentSending}
                  />
                  <button
                    className="btn-secondary text-sm px-3 disabled:opacity-50"
                    onClick={sendComment}
                    disabled={commentSending || !newComment.trim()}
                  >
                    {commentSending ? "..." : "Enviar"}
                  </button>
                </div>
              </div>

              {/* Caixa de resposta */}
              <div className="mt-6 border-t pt-4">
                {/* Responder para (editável) */}
                <div className="mb-2">
                  <label className="text-xs text-gray-500 uppercase font-medium">Responder para:</label>
                  <div className="mt-1 flex flex-wrap gap-1 items-center border rounded px-2 py-1.5 bg-white focus-within:ring-1 focus-within:ring-blue-400">
                    {replyTo.map((email) => (
                      <span key={email} className="inline-flex items-center gap-1 bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded-full">
                        {email}
                        <button
                          type="button"
                          className="text-blue-500 hover:text-red-500 leading-none"
                          onClick={() => setReplyTo(prev => prev.filter(e => e !== email))}
                        >×</button>
                      </span>
                    ))}
                    <input
                      className="flex-1 min-w-24 text-sm outline-none"
                      placeholder="Adicionar destinatário..."
                      value={replyToInput}
                      disabled={replySending}
                      onChange={e => setReplyToInput(e.target.value)}
                      onKeyDown={e => {
                        if ((e.key === "Enter" || e.key === ",") && replyToInput.trim()) {
                          e.preventDefault();
                          const email = replyToInput.trim().replace(/,$/, "");
                          if (email && !replyTo.includes(email)) setReplyTo(prev => [...prev, email]);
                          setReplyToInput("");
                        }
                        if (e.key === "Backspace" && !replyToInput && replyTo.length > 0) {
                          setReplyTo(prev => prev.slice(0, -1));
                        }
                      }}
                      onBlur={() => {
                        const email = replyToInput.trim().replace(/,$/, "");
                        if (email && !replyTo.includes(email)) setReplyTo(prev => [...prev, email]);
                        setReplyToInput("");
                      }}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2 mb-2">
                  <label className="text-xs text-gray-500 uppercase font-medium whitespace-nowrap">CC:</label>
                  <input
                    className="input text-sm flex-1"
                    placeholder="email1@exemplo.com, email2@exemplo.com"
                    value={replyCc}
                    onChange={(e) => setReplyCc(e.target.value)}
                    disabled={replySending}
                  />
                </div>
                <textarea
                  className="input w-full mt-1 text-sm"
                  rows={5}
                  placeholder="Digite sua resposta..."
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  disabled={replySending}
                />
                {/* Anexos na resposta */}
                <div className="mt-2">
                  <input type="file" multiple className="text-sm w-full" disabled={replySending} onChange={e => {
                    const files = Array.from(e.target.files ?? []);
                    const tooBig = files.filter(f => f.size > 10 * 1024 * 1024);
                    if (tooBig.length) { toast(`Arquivo muito grande (máx 10MB): ${tooBig[0].name}`, "error"); return; }
                    setReplyFiles(files);
                  }} />
                  {replyFiles.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {replyFiles.map((f, i) => (
                        <span key={i} className="inline-flex items-center gap-1 bg-gray-100 text-gray-700 text-xs px-2 py-0.5 rounded-full">
                          📎 {f.name}
                          <button type="button" onClick={() => setReplyFiles(prev => prev.filter((_, j) => j !== i))} className="text-gray-400 hover:text-red-500">×</button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
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

        <div className={`col-span-12 md:col-span-3 card overflow-y-auto ${!selected ? "hidden md:block" : "block"}`}>
          {!selected ? (
            <div className="p-4 text-sm text-gray-500">—</div>
          ) : (
            <div className="p-4 space-y-3 text-sm">
              <h3 className="font-semibold text-base mb-2">Dados da demanda</h3>
              <Field label="Responsável" value={selected.assigned_user?.name || "—"} />
              {/* Co-responsáveis */}
              <div>
                <div className="text-xs uppercase text-gray-500 mb-1">Co-responsáveis</div>
                <div className="space-y-1">
                  {(selected.co_assignees ?? []).length === 0 && (
                    <div className="text-xs text-gray-400">Nenhum</div>
                  )}
                  {(selected.co_assignees ?? []).map(c => (
                    <div key={c.share_id} className="flex items-center justify-between bg-gray-50 rounded px-2 py-1">
                      <span className="text-xs text-gray-700">{c.user.name}</span>
                      {(isAdmin || selected.assigned_user?.id === me?.id || c.user.id === me?.id) && (
                        <button
                          className="text-xs text-red-400 hover:text-red-600"
                          title="Remover co-responsável"
                          onClick={async () => {
                            try {
                              const updated = await api.coUnassign(selected.id, c.share_id);
                              setSelected(prev => prev ? { ...prev, co_assignees: (updated as any).co_assignees ?? [] } : prev);
                            } catch (e: any) { toast(e.message, "error"); }
                          }}
                        >×</button>
                      )}
                    </div>
                  ))}
                </div>
                {/* Adicionar co-responsável */}
                {(isAdmin || selected.assigned_user?.id === me?.id) && (
                  <select
                    className="input text-xs mt-2"
                    value=""
                    onChange={async (e) => {
                      const uid = Number(e.target.value);
                      if (!uid) return;
                      try {
                        const updated = await api.coAssign(selected.id, uid);
                        setSelected(prev => prev ? { ...prev, co_assignees: (updated as any).co_assignees ?? [] } : prev);
                        toast("Co-responsável adicionado.", "success");
                      } catch (e: any) { toast(e.message, "error"); }
                    }}
                  >
                    <option value="">+ Adicionar co-responsável...</option>
                    {users.filter(u => u.active && u.id !== selected.assigned_user?.id && !(selected.co_assignees ?? []).some(c => c.user.id === u.id)).map(u => (
                      <option key={u.id} value={u.id}>{u.name}</option>
                    ))}
                  </select>
                )}
              </div>
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
