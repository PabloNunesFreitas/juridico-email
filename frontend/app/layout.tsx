import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Gestão de E-mails Jurídicos",
  description: "PoC interno de gestão de demandas",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
