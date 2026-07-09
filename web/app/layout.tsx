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
  themeColor: "#0f4c3a",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        {/* Liquid Glass 굴절용 전역 SVG 필터(Chromium backdrop-filter: url()). */}
        <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
          <filter id="liquid-glass" x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.008 0.012"
              numOctaves={2}
              seed={7}
              result="noise"
            />
            <feGaussianBlur in="noise" stdDeviation="1.5" result="soft" />
            <feDisplacementMap
              in="SourceGraphic"
              in2="soft"
              scale="24"
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>
        </svg>
        {children}
        <Footer />
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
