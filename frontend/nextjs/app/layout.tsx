import type { Metadata, Viewport } from "next";
import { ResearchHistoryProvider } from "@/hooks/ResearchHistoryContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "Traceable Deep Researcher",
  description: "支持网络与本地文档研究的自托管应用，提供带来源引用的研究报告。",
  manifest: "/manifest.json",
  icons: { icon: "/img/brand-mark.svg", apple: "/img/brand-mark-192.png" },
  appleWebApp: { capable: true, statusBarStyle: "default", title: "Traceable Deep Researcher" },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#111827" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html className="tdr-root" lang="zh-CN" suppressHydrationWarning>
      <body className="app-container flex min-h-screen flex-col justify-between" suppressHydrationWarning>
        <ResearchHistoryProvider>{children}</ResearchHistoryProvider>
      </body>
    </html>
  );
}
