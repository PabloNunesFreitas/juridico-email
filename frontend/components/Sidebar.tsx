"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api, User } from "@/lib/api";

const items = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/inbox", label: "Caixa de Entrada", admin: true },
  { href: "/my-demands", label: "Minhas Solicitações" },
  { href: "/unassigned", label: "Não atribuídas" },
  { href: "/archive", label: "Arquivo Morto" },
  { href: "/users", label: "Usuários", admin: true },
  { href: "/logs", label: "Logs", admin: true },
  { href: "/settings", label: "Configurações", admin: true },
];

export function Sidebar({ user }: { user: User | null }) {
  const path = usePathname();
  const isAdmin = user?.role === "ADMIN";
  return (
    <aside className="w-60 shrink-0 bg-gray-900 text-gray-100 min-h-screen flex flex-col">
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="text-sm uppercase tracking-wider text-gray-400">Jurídico</div>
        <div className="font-semibold text-lg">E-mails</div>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {items.filter((i) => !i.admin || isAdmin).map((i) => {
          const active = path?.startsWith(i.href);
          return (
            <Link key={i.href} href={i.href} className={`block px-3 py-2 rounded-md text-sm ${active ? "bg-blue-600 text-white" : "hover:bg-gray-800"}`}>
              {i.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-800 text-sm">
        {user && (
          <>
            <div className="font-medium truncate">{user.name}</div>
            <div className="text-gray-400 text-xs truncate">{user.email}</div>
            <div className="text-xs text-gray-500 mt-1">{user.role}</div>
            <button className="mt-3 text-xs text-red-400 hover:text-red-300" onClick={() => api.logout()}>Sair</button>
          </>
        )}
      </div>
    </aside>
  );
}
