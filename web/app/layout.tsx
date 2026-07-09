import "./globals.css";
import type { Metadata, Viewport } from "next";
import Footer from "../components/Footer";
import ServiceWorkerRegister from "../components/ServiceWorkerRegister";

export const metadata: Metadata = {
  title: "오늘의 뉴스 다이제스트",
  description: "매일 아침 사실 중심으로 요약한 뉴스 다이제스트",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "뉴스 다이제스트",
    statusBarStyle: "default",
  },
  icons: {
    icon: "/icons/icon-192.png",
    apple: "/icons/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#1257a8",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        {children}
        <Footer />
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
