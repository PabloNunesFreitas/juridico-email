"use client";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api, Folder, User } from "@/lib/api";
import { THEMES, ThemeId, getTheme, setTheme, getThemeConfig } from "@/lib/theme";
import { NotificationBell } from "@/components/NotificationBell";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/inbox", label: "Caixa de Entrada", admin: true },
  { href: "/my-demands", label: "Minhas Solicitações" },
  { href: "/shared", label: "Compartilhadas comigo" },
  { href: "/unassigned", label: "Não atribuídas" },
];

export function Sidebar({ user, isOpen, onClose }: { user: User | null; isOpen?: boolean; onClose?: () => void }) {
  const path = usePathname();
  const isAdmin = user?.role === "ADMIN";
  const [themeId, setThemeId] = useState<ThemeId>("cinza");
  const [folders, setFolders] = useState<Folder[]>([]);
  const [archivedCount, setArchivedCount] = useState(0);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renamingName, setRenamingName] = useState("");

  useEffect(() => {
    const saved = user?.theme || getTheme();
    setThemeId((saved as ThemeId) || "cinza");
    const handler = () => setThemeId(getTheme());
    window.addEventListener("themechange", handler);
    return () => window.removeEventListener("themechange", handler);
  }, [user?.theme]);

  async function refreshFolders() {
    try {
      const [f, a] = await Promise.all([
        api.listFolders(),
        api.archivedCount(),
      ]);
      setFolders(f);
      setArchivedCount(a.count);
    } catch {}
  }

  useEffect(() => {
    if (!user) return;
    refreshFolders();
    const handler = () => refreshFolders();
    window.addEventListener("folderchange", handler);
    window.addEventListener("archivechange", handler);
    return () => {
      window.removeEventListener("folderchange", handler);
      window.removeEventListener("archivechange", handler);
    };
  }, [user]);

  async function createFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      await api.createFolder(name);
      setNewFolderName("");
      setCreatingFolder(false);
      refreshFolders();
      window.dispatchEvent(new Event("folderchange"));
    } catch {}
  }

  async function renameFolder() {
    if (!renamingId || !renamingName.trim()) { setRenamingId(null); return; }
    try {
      await api.renameFolder(renamingId, renamingName.trim());
      setRenamingId(null);
      refreshFolders();
      window.dispatchEvent(new Event("folderchange"));
    } catch { setRenamingId(null); }
  }

  async function deleteFolder(folder: Folder) {
    if (!confirm(`Excluir pasta "${folder.name}"?\nAs demandas voltarão para a caixa de entrada.`)) return;
    try {
      await api.deleteFolder(folder.id);
      refreshFolders();
      window.dispatchEvent(new Event("folderchange"));
    } catch {}
  }

  const theme = getThemeConfig(themeId);

  return (
    <aside className={`fixed md:relative inset-y-0 left-0 z-50 md:z-auto w-60 shrink-0 ${theme.sidebar} text-gray-100 min-h-screen flex flex-col transition-transform duration-200 ease-in-out ${isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}`}>
      <div className="px-4 py-4 border-b border-white/10 flex items-center justify-between gap-2">
        <div className="bg-white rounded-lg px-2 py-1.5 shadow-sm">
          <Image src="/logo.png" alt="Andrade Alves Advogados" width={130} height={48} className="object-contain" priority />
        </div>
        <div className="flex items-center gap-1">
          <NotificationBell />
          <button
            className="md:hidden text-gray-400 hover:text-white p-1 rounded"
            onClick={onClose}
            aria-label="Fechar menu"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {/* Navegação principal */}
        {NAV_ITEMS.filter((i) => !i.admin || isAdmin).map((i) => {
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
        {isAdmin && (
          <>
            <Link href="/users" className={`block px-3 py-2 rounded-md text-sm ${path?.startsWith("/users") ? `${theme.active} text-white` : theme.hover}`}>Usuários</Link>
            <Link href="/logs" className={`block px-3 py-2 rounded-md text-sm ${path?.startsWith("/logs") ? `${theme.active} text-white` : theme.hover}`}>Logs</Link>
            <Link href="/settings" className={`block px-3 py-2 rounded-md text-sm ${path?.startsWith("/settings") ? `${theme.active} text-white` : theme.hover}`}>Configurações</Link>
          </>
        )}

        {/* Arquivo Morto */}
        <div className="pt-2 pb-1">
          <Link
            href="/archive"
            className={`flex items-center justify-between px-3 py-2 rounded-md text-sm ${path?.startsWith("/archive") ? `${theme.active} text-white` : theme.hover}`}
          >
            <span>📦 Arquivo Morto</span>
            {archivedCount > 0 && (
              <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 min-w-[1.25rem] text-center font-medium leading-none">
                {archivedCount > 99 ? "99+" : archivedCount}
              </span>
            )}
          </Link>
        </div>

        {/* Seção de pastas */}
        <div className="pt-2">
          <div className="flex items-center justify-between px-3 py-1">
            <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">Pastas</span>
            <button
              onClick={() => { setCreatingFolder(true); setNewFolderName(""); }}
              className="text-gray-400 hover:text-white text-xl leading-none w-5 h-5 flex items-center justify-center rounded transition-colors"
              title="Nova pasta"
            >+</button>
          </div>

          {creatingFolder && (
            <div className="px-3 pb-2 flex gap-1 mt-1">
              <input
                className="flex-1 text-sm bg-white/10 rounded px-2 py-1 text-white placeholder-gray-500 outline-none border border-white/20 focus:border-white/40"
                placeholder="Nome da pasta..."
                autoFocus
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter") createFolder();
                  if (e.key === "Escape") setCreatingFolder(false);
                }}
              />
              <button onClick={createFolder} className="text-green-400 hover:text-green-300 px-1 text-sm">✓</button>
              <button onClick={() => setCreatingFolder(false)} className="text-gray-400 hover:text-white px-1 text-sm">✕</button>
            </div>
          )}

          {folders.length === 0 && !creatingFolder && (
            <p className="px-3 py-1 text-xs text-gray-500 italic">Nenhuma pasta. Clique em + para criar.</p>
          )}

          {folders.map(folder => (
            <div key={folder.id} className="group relative flex items-center">
              {renamingId === folder.id ? (
                <div className="flex-1 px-3 py-1 flex gap-1">
                  <input
                    className="flex-1 text-sm bg-white/10 rounded px-2 py-0.5 text-white placeholder-gray-500 outline-none border border-white/20"
                    value={renamingName}
                    autoFocus
                    onChange={e => setRenamingName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === "Enter") renameFolder();
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    onBlur={renameFolder}
                  />
                </div>
              ) : (
                <Link
                  href={`/folder/${folder.id}`}
                  className={`flex-1 flex items-center gap-2 px-3 py-1.5 rounded-md text-sm mr-10 ${path === `/folder/${folder.id}` ? `${theme.active} text-white` : theme.hover}`}
                >
                  <span className="text-gray-400 text-sm">📁</span>
                  <span className="flex-1 truncate text-sm">{folder.name}</span>
                  {folder.demand_count > 0 && (
                    <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 min-w-[1.25rem] text-center font-medium leading-none shrink-0">
                      {folder.demand_count > 99 ? "99+" : folder.demand_count}
                    </span>
                  )}
                </Link>
              )}
              {renamingId !== folder.id && (
                <div className="absolute right-1 hidden group-hover:flex gap-0.5 bg-transparent">
                  <button
                    onClick={e => { e.preventDefault(); setRenamingId(folder.id); setRenamingName(folder.name); }}
                    className="text-gray-400 hover:text-white p-1 text-xs rounded hover:bg-white/10"
                    title="Renomear"
                  >✏</button>
                  <button
                    onClick={e => { e.preventDefault(); deleteFolder(folder); }}
                    className="text-gray-400 hover:text-red-400 p-1 text-xs rounded hover:bg-white/10"
                    title="Excluir pasta"
                  >✕</button>
                </div>
              )}
            </div>
          ))}
        </div>
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
