"use client";
import { useEffect, useRef, useState } from "react";
import { api, Notification } from "@/lib/api";
import { fmtDateTime } from "@/lib/date";

export function NotificationBell() {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  const prevCount = useRef(0);
  const audioCtxRef = useRef<AudioContext | null>(null);

  function playSound() {
    try {
      if (!audioCtxRef.current) audioCtxRef.current = new AudioContext();
      const ctx = audioCtxRef.current;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.12);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.45);
    } catch {}
  }

  async function loadCount() {
    try {
      const { count: n } = await api.unreadCount();
      if (n > prevCount.current) playSound();
      prevCount.current = n;
      setCount(n);
    } catch {}
  }

  async function openPanel() {
    const next = !open;
    setOpen(next);
    if (next) {
      try {
        const data = await api.listNotifications();
        setItems(data);
        if (data.some(n => !n.read)) {
          await api.markAllRead();
          setCount(0);
        }
      } catch {}
    }
  }

  useEffect(() => {
    loadCount();
    const id = setInterval(loadCount, 20_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const TYPE_LABEL: Record<string, string> = {
    DEMAND_ASSIGNED: "Atribuição",
    DEMAND_SHARED: "Compartilhamento",
    COMMENT_ADDED: "Comentário",
    COMMENT_MENTION: "Menção",
    DEMAND_MOVED_TO_FOLDER: "Movida para pasta",
    NEW_EMAIL_IN_FOLDER: "Novo e-mail em pasta",
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={openPanel}
        className="relative flex items-center justify-center w-8 h-8 rounded-full hover:bg-white/10 transition-colors"
        title="Notificações"
      >
        <span className="text-lg">🔔</span>
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-red-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-xl z-50">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <span className="font-semibold text-sm text-gray-800">Notificações</span>
            {items.length > 0 && (
              <button
                className="text-xs text-blue-600 hover:underline"
                onClick={async () => { await api.markAllRead(); setCount(0); setItems(prev => prev.map(n => ({ ...n, read: true }))); }}
              >Marcar todas como lidas</button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto divide-y divide-gray-50">
            {items.length === 0 && (
              <p className="px-4 py-6 text-sm text-gray-400 text-center">Nenhuma notificação.</p>
            )}
            {items.map(n => (
              <div
                key={n.id}
                className={`px-4 py-3 text-sm ${n.read ? "bg-white" : "bg-blue-50"}`}
              >
                <div className="flex items-start gap-2">
                  <span className={`mt-0.5 text-xs font-medium px-1.5 py-0.5 rounded ${n.read ? "bg-gray-100 text-gray-500" : "bg-blue-100 text-blue-700"}`}>
                    {TYPE_LABEL[n.type] || n.type}
                  </span>
                </div>
                <p className="text-gray-700 mt-1 leading-snug">{n.message}</p>
                <p className="text-gray-400 text-xs mt-1">{fmtDateTime(n.created_at)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
