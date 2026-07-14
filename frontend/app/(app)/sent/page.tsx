"use client";
import { useEffect, useState } from "react";
import { api, SentEmail, DemandDetail, User } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/date";

export default function SentPage() {
  const [items, setItems] = useState<SentEmail[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DemandDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    api.me().then(setMe).catch(() => {});
    api.sentEmails().then(setItems).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const isAdmin = me?.role === "ADMIN";

  async function openThread(m: SentEmail) {
    setSelectedId(m.id);
    setLoadingDetail(true);
    setDetail(null);
    try {
      setDetail(await api.getDemand(m.demand_id));
    } catch {
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }

  async function openAttachment(messageId: number, att: { id: number; filename: string }) {
    try {
      const blob = await api.fetchAttachmentBlob(messageId, att.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const viewable = /\.(pdf|png|jpe?g|gif|webp|bmp|svg)$/i.test(att.filename || "");
      if (viewable) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
      else { a.download = att.filename || "anexo"; }
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch { alert("Não foi possível abrir o anexo."); }
  }

  function bodyOf(msg: DemandDetail["messages"][number]): string {
    if (msg.body_text) return msg.body_text;
    if (msg.body_html) return msg.body_html.replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    return "(sem conteúdo)";
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">📤 E-mails enviados</h1>
      <p className="text-sm text-gray-500 mb-4">
        {isAdmin
          ? "Todos os e-mails enviados pela equipe. Clique para ver o conteúdo e o histórico do caso."
          : "Os e-mails que você enviou. Clique para ver o conteúdo e o histórico do caso."}
      </p>

      {loading ? (
        <p className="text-sm text-gray-400">Carregando...</p>
      ) : items.length === 0 ? (
        <div className="card p-6 text-sm text-gray-500">
          Nenhum e-mail enviado ainda. O que você responder ou compor pelo sistema aparecerá aqui.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Lista de enviados */}
          <div className="card divide-y max-h-[72vh] overflow-y-auto">
            {items.map((m) => (
              <button
                key={m.id}
                onClick={() => openThread(m)}
                className={`w-full text-left p-3 hover:bg-gray-50 transition-colors ${selectedId === m.id ? "bg-blue-50" : ""}`}
              >
                <div className="flex justify-between gap-2">
                  <span className="font-medium text-sm truncate">{m.subject || "(sem assunto)"}</span>
                  <span className="text-xs text-gray-400 whitespace-nowrap">{fmtDate(m.received_at)}</span>
                </div>
                <div className="text-xs text-gray-600 truncate">Para: {m.recipient_emails || "—"}</div>
                {isAdmin && <div className="text-xs text-gray-400">Enviado por: {m.sent_by_name || "—"}</div>}
              </button>
            ))}
          </div>

          {/* Detalhe: conteúdo + histórico do caso */}
          <div className="card p-3 max-h-[72vh] overflow-y-auto">
            {!selectedId ? (
              <p className="text-sm text-gray-400">Selecione um e-mail à esquerda para ver o conteúdo e o histórico.</p>
            ) : loadingDetail ? (
              <p className="text-sm text-gray-400">Carregando...</p>
            ) : !detail ? (
              <p className="text-sm text-gray-400">Não foi possível carregar o caso.</p>
            ) : (
              <div>
                <h2 className="font-semibold text-sm mb-1">{detail.subject || "(sem assunto)"}</h2>
                <p className="text-xs text-gray-400 mb-3">{detail.messages.length} mensagem(ns) no histórico</p>
                <div className="space-y-2">
                  {detail.messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`rounded-lg p-2 ${msg.direction === "out" ? "bg-blue-50 border-l-4 border-blue-400" : "bg-gray-50 border border-gray-100"}`}
                    >
                      <div className="flex justify-between text-xs text-gray-500">
                        <span className="font-medium">
                          {msg.direction === "out"
                            ? `↗ Enviado${msg.sender_name ? " por " + msg.sender_name : ""}`
                            : (msg.sender_name || msg.sender_email)}
                        </span>
                        <span>{fmtDateTime(msg.received_at)}</span>
                      </div>
                      {msg.recipient_emails && <div className="text-xs text-gray-400">Para: {msg.recipient_emails}</div>}
                      {msg.cc_emails && <div className="text-xs text-gray-400">Cópia: {msg.cc_emails}</div>}
                      <pre className="text-sm whitespace-pre-wrap mt-1 text-gray-800 font-sans">{bodyOf(msg)}</pre>
                      {msg.attachments && msg.attachments.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {msg.attachments.map((att) => (
                            <button
                              key={att.id}
                              onClick={() => openAttachment(msg.id, att)}
                              className="text-xs text-blue-600 hover:text-blue-800 bg-blue-50 px-2 py-0.5 rounded"
                            >📎 {att.filename}</button>
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
      )}
    </div>
  );
}
