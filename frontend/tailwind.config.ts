import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  safelist: [
    "bg-gray-900", "hover:bg-gray-800",
    "bg-blue-950", "hover:bg-blue-900", "bg-blue-500",
    "bg-purple-950", "hover:bg-purple-900", "bg-purple-600",
    "bg-emerald-950", "hover:bg-emerald-900", "bg-emerald-600",
  ],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
