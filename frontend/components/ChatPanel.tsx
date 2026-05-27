"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ChatMention } from "@/lib/api";

export function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [mentions, setMentions] = useState<ChatMention[]>([]);
  const [count, setCount] = useState(0);
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);

  async function load() {
    try {
      const data = await api.chatMentions();
      setMentions(data);
      setCount(data.length);
    } catch {}
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function goToDemand(demandId: number) {
    setOpen(false);
    router.push(`/inbox?demand=${demandId}`);
  }

  async function dismiss(notificationId: number, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await api.dismissMention(notificationId);
      setMentions(prev => prev.filter(m => m.notification_id !== notificationId));
      setCount(prev => Math.max(0, prev - 1));
    } catch {}
  }

  return (
    <div ref={ref} className="fixed bottom-6 right-6 z-50">
      {/* Painel deslizante */}
      {open && (
        <div className="absolute bottom-14 right-0 w-80 bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden">
          <div className="px-4 py-3 bg-blue-600 text-white flex items-center justify-between">
            <span className="font-semibold text-sm">💬 Menções pendentes</span>
            <button onClick={() => setOpen(false)} className="text-blue-200 hover:text-white text-lg leading-none">×</button>
          </div>

          <div className="overflow-y-auto max-h-96">
            {mentions.length === 0 ? (
              <div className="p-6 text-sm text-gray-400 text-center">
                Nenhuma menção pendente.<br />
                <span className="text-xs">Você respondeu tudo! ✅</span>
              </div>
            ) : (
              mentions.map(m => (
                <div key={m.notification_id} className="flex items-stretch border-b border-gray-100 last:border-0 hover:bg-blue-50 transition-colors group">
                  <button
                    onClick={() => goToDemand(m.demand_id)}
                    className="flex-1 text-left px-4 py-3"
                  >
                    <div className="flex items-start gap-2">
                      <span className="text-yellow-500 text-base mt-0.5 shrink-0">⏳</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-gray-800 truncate">{m.demand_subject}</p>
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{m.message}</p>
                        <p className="text-[10px] text-gray-400 mt-1">{new Date(m.created_at).toLocaleString("pt-BR")}</p>
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={(e) => dismiss(m.notification_id, e)}
                    className="px-3 text-gray-300 hover:text-red-400 transition-colors self-center text-lg leading-none opacity-0 group-hover:opacity-100"
                    title="Dispensar"
                  >×</button>
                </div>
              ))
            )}
          </div>

          {mentions.length > 0 && (
            <div className="px-4 py-2 border-t bg-gray-50 text-xs text-gray-500 text-center">
              Clique para ir à demanda e responder
            </div>
          )}
        </div>
      )}

      {/* Botão flutuante */}
      <button
        onClick={() => { setOpen(v => !v); if (!open) load(); }}
        className="w-12 h-12 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-105 relative"
        title="Menções pendentes"
      >
        <span className="text-xl">💬</span>
        {count > 0 && (
          <span className="absolute -top-1 -right-1 bg-yellow-400 text-gray-900 text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center leading-none shadow">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>
    </div>
  );
}
