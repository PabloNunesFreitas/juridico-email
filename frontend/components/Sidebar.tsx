"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api, User } from "@/lib/api";
import { THEMES, ThemeId, getTheme, setTheme, getThemeConfig } from "@/lib/theme";
import { NotificationBell } from "@/components/NotificationBell";

const items = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/inbox", label: "Caixa de Entrada", admin: true },
  { href: "/my-demands", label: "Minhas Solicitações" },
  { href: "/shared", label: "Compartilhadas comigo" },
  { href: "/unassigned", label: "Não atribuídas" },
  { href: "/archive", label: "Arquivo Morto" },
  { href: "/users", label: "Usuários", admin: true },
  { href: "/logs", label: "Logs", admin: true },
  { href: "/settings", label: "Configurações", admin: true },
];

export function Sidebar({ user }: { user: User | null }) {
  const path = usePathname();
  const isAdmin = user?.role === "ADMIN";
  const [themeId, setThemeId] = useState<ThemeId>("cinza");

  useEffect(() => {
    const saved = user?.theme || getTheme();
    setThemeId((saved as ThemeId) || "cinza");
    const handler = () => setThemeId(getTheme());
    window.addEventListener("themechange", handler);
    return () => window.removeEventListener("themechange", handler);
  }, [user?.theme]);

  const theme = getThemeConfig(themeId);

  return (
    <aside className={`w-60 shrink-0 ${theme.sidebar} text-gray-100 min-h-screen flex flex-col`}>
      <div className="px-5 py-5 border-b border-white/10 flex items-center justify-between">
        <div>
          <div className="text-sm uppercase tracking-wider text-gray-400">Jurídico</div>
          <div className="font-semibold text-lg">E-mails</div>
        </div>
        <NotificationBell />
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {items.filter((i) => !i.admin || isAdmin).map((i) => {
          const active = path?.startsWith(i.href);
          return (
            <Link
              key={i.href}
              href={i.href}
              className={`block px-3 py-2 rounded-md text-sm ${active ? `${theme.active} text-white` : `${theme.hover}`}`}
            >
              {i.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-white/10 text-sm">
        {user && (
          <>
            <div className="font-medium truncate">{user.name}</div>
            <div className="text-gray-400 text-xs truncate">{user.email}</div>
            <div className="text-xs text-gray-500 mt-1">{user.role}</div>
            <button className="mt-3 text-xs text-red-400 hover:text-red-300" onClick={() => api.logout()}>Sair</button>
          </>
        )}
        <div className="mt-4 border-t border-white/10 pt-3">
          <p className="text-xs text-gray-500 mb-2">Tema</p>
          <div className="flex gap-1.5">
            {THEMES.map(t => (
              <button
                key={t.id}
                title={t.label}
                onClick={() => { setTheme(t.id); api.setTheme(t.id).catch(() => {}); }}
                className={`w-5 h-5 rounded-full border-2 transition-all ${themeId === t.id ? "border-white scale-110" : "border-transparent opacity-60 hover:opacity-100"}`}
                style={{ backgroundColor: t.dot }}
              />
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
