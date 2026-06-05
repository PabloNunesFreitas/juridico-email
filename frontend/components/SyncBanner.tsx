"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

type Status = Awaited<ReturnType<typeof api.syncStatus>>;

export function SyncBanner() {
  const [s, setS] = useState<Status | null>(null);
  const lastFinishedAtRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const data = await api.syncStatus();
        if (!alive) return;
        const now = Date.now();
        const justFinished =
          data.finished_at &&
          data.finished_at !== lastFinishedAtRef.current &&
          now - new Date(data.finished_at).getTime() < 8000;
        const finishedRecently =
          data.finished_at && now - new Date(data.finished_at).getTime() < 8000;

        if (data.running || finishedRecently) {
          setS(data);
        } else {
          setS(null);
        }

        if (justFinished && !data.running) {
          lastFinishedAtRef.current = data.finished_at!;
          if (data.new_demands > 0) {
            toast(`${data.new_demands} nova(s) demanda(s) recebida(s)`, "info");
            if (typeof Notification !== "undefined" && Notification.permission === "granted") {
              new Notification("Novos e-mails", {
                body: `${data.new_demands} nova(s) demanda(s) chegaram`,
              });
            }
          }
        }
      } catch {}
    }
    tick();
    const id = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!s) return null;
  const pct = s.to_fetch > 0 ? Math.min(100, Math.round((s.fetched / s.to_fetch) * 100)) : 0;
  const isDone = !s.running && s.finished_at;

  return (
    <div className={`sticky top-0 z-30 ${isDone ? (s.error ? "bg-red-50 border-red-200" : "bg-green-50 border-green-200") : "bg-blue-50 border-blue-200"} border-b px-4 py-2 text-sm flex items-center gap-3`}>
      {s.running ? (
        s.to_fetch === 0 ? (
          <>
            <div className="animate-pulse w-2 h-2 rounded-full bg-blue-500" />
            <div className="font-medium">Verificando quantas mensagens existem na caixa…</div>
          </>
        ) : (
          <>
            <div className="animate-pulse w-2 h-2 rounded-full bg-blue-500" />
            <div className="font-medium">Baixando e-mails ({s.scanned} encontrados, {s.to_fetch} novos)…</div>
            <div className="flex-1 max-w-md">
              <div className="h-1.5 bg-blue-100 rounded">
                <div className="h-1.5 bg-blue-600 rounded transition-all" style={{ width: `${pct}%` }} />
              </div>
            </div>
            <div className="text-blue-900 font-mono text-xs">{s.fetched}/{s.to_fetch} ({pct}%)</div>
            {s.last_message && <div className="text-gray-500 truncate max-w-xs hidden md:block">↳ {s.last_message}</div>}
          </>
        )
      ) : s.error ? (
        <span className="text-red-700">⚠ Erro na sincronização: {s.error}</span>
      ) : (
        <span className="text-green-700">✓ Sincronização concluída — {s.new_messages} mensagens novas, {s.new_demands} demandas.</span>
      )}
    </div>
  );
}
