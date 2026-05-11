"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Status = Awaited<ReturnType<typeof api.syncStatus>>;

export function SyncBanner() {
  const [s, setS] = useState<Status | null>(null);

  useEffect(() => {
    let alive = true;
    let lastFinishedAt: string | null = null;
    async function tick() {
      try {
        const data = await api.syncStatus();
        if (!alive) return;
        // Só mostra se está rodando OU se acabou nos últimos 8s
        const now = Date.now();
        const finishedRecently = data.finished_at && now - new Date(data.finished_at).getTime() < 8000 && data.finished_at !== lastFinishedAt;
        if (data.running || finishedRecently) {
          setS(data);
          if (data.finished_at && !data.running) lastFinishedAt = data.finished_at;
        } else {
          setS(null);
        }
      } catch {}
    }
    tick();
    const id = setInterval(tick, 1500);
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
        <>
          <span className="text-red-700">⚠ Erro na sincronização: {s.error}</span>
        </>
      ) : (
        <>
          <span className="text-green-700">✓ Sincronização concluída — {s.new_messages} mensagens novas, {s.new_demands} demandas.</span>
        </>
      )}
    </div>
  );
}
