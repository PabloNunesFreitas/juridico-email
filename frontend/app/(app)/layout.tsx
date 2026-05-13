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

  useEffect(() => {
    const t = localStorage.getItem("token");
    if (!t) {
      router.replace("/login");
      return;
    }
    api.me().then(setUser).catch(() => router.replace("/login")).finally(() => setLoading(false));
  }, [router]);

  if (loading) return <div className="min-h-screen flex items-center justify-center text-gray-500">Carregando...</div>;
  return (
    <div className="flex">
      <Sidebar user={user} />
      <main className="flex-1 min-h-screen">
        <SyncBanner />
        <div className="p-6">{children}</div>
      </main>
      <Toaster />
    </div>
  );
}
