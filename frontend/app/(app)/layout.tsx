"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { SyncBanner } from "@/components/SyncBanner";
import { Toaster } from "@/components/Toaster";
import { api, User } from "@/lib/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("token");
    if (!t) { router.replace("/login"); return; }
    api.me().then(setUser).catch(() => router.replace("/login")).finally(() => setLoading(false));
  }, [router]);

  if (loading) return <div className="min-h-screen flex items-center justify-center text-gray-500">Carregando...</div>;
  return (
    <div className="flex">
      <Sidebar user={user} isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      <main className="flex-1 min-h-screen overflow-x-hidden">
        <div className="md:hidden flex items-center gap-3 px-4 py-3 border-b bg-white sticky top-0 z-30 shadow-sm">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-gray-600 hover:text-gray-900 p-1 -ml-1"
            aria-label="Abrir menu"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <span className="font-semibold text-gray-800 text-sm">Andrade Alves</span>
        </div>
        <SyncBanner />
        <div className="p-3 md:p-6">{children}</div>
      </main>
      <Toaster />
    </div>
  );
}
