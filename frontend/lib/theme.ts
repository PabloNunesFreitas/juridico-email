export const THEMES = [
  {
    id: "cinza",
    label: "Cinza",
    sidebar: "bg-gray-900",
    hover: "hover:bg-gray-800",
    active: "bg-blue-600",
    dot: "#374151",
  },
  {
    id: "azul",
    label: "Azul",
    sidebar: "bg-blue-950",
    hover: "hover:bg-blue-900",
    active: "bg-blue-500",
    dot: "#172554",
  },
  {
    id: "roxo",
    label: "Roxo",
    sidebar: "bg-purple-950",
    hover: "hover:bg-purple-900",
    active: "bg-purple-600",
    dot: "#3b0764",
  },
  {
    id: "verde",
    label: "Verde",
    sidebar: "bg-emerald-950",
    hover: "hover:bg-emerald-900",
    active: "bg-emerald-600",
    dot: "#022c22",
  },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];

export function getTheme(): ThemeId {
  if (typeof window === "undefined") return "cinza";
  return (localStorage.getItem("sidebarTheme") as ThemeId) || "cinza";
}

export function setTheme(id: ThemeId) {
  localStorage.setItem("sidebarTheme", id);
  window.dispatchEvent(new Event("themechange"));
}

export function getThemeConfig(id: ThemeId) {
  return THEMES.find(t => t.id === id) ?? THEMES[0];
}
