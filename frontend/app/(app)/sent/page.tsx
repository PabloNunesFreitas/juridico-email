"use client";
import { useEffect, useState } from "react";
import { api, SentEmail, User } from "@/lib/api";

export default function SentPage() {
  const [items, setItems] = useState<SentEmail[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me().then(setMe).catch(() => {});
    api.sentEmails().then(setItems).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const isAdmin = me?.role === "ADMIN";

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">📤 E-mails enviados</h1>
      <p className="text-sm text-gray-500 mb-4">
        {isAdmin
          ? "Todos os e-mails enviados pela equipe pelo sistema."
          : "Os e-mails que você enviou pelo sistema."}
      </p>

      {loading ? (
        <p className="text-sm text-gray-400">Carregando...</p>
      ) : items.length === 0 ? (
        <div className="card p-6 text-sm text-gray-500">
          Nenhum e-mail enviado ainda. Os e-mails que você responder ou compor pelo sistema aparecerão aqui.
        </div>
      ) : (
        <div className="card divide-y">
          {items.map((m) => (
            <div key={m.id} className="p-3">
              <div className="flex justify-between gap-2">
                <span className="font-medium text-sm truncate">{m.subject || "(sem assunto)"}</span>
                <span className="text-xs text-gray-400 whitespace-nowrap">
                  {new Date(m.received_at).toLocaleString()}
                </span>
              </div>
              <div className="text-xs text-gray-600 mt-0.5">Para: {m.recipient_emails || "—"}</div>
              {m.cc_emails && <div className="text-xs text-gray-500">Cópia: {m.cc_emails}</div>}
              {isAdmin && (
                <div className="text-xs text-gray-400 mt-0.5">
                  Enviado por: <span className="font-medium">{m.sent_by_name || "—"}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
