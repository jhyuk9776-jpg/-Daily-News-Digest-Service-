import type { MetadataRoute } from "next";

// Next가 /manifest.webmanifest 로 자동 서빙한다(layout metadata.manifest와 연결).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "오늘의 뉴스 다이제스트",
    short_name: "뉴스 다이제스트",
    description: "매일 아침 사실 중심으로 요약한 뉴스 다이제스트",
    start_url: "/",
    display: "standalone",
    background_color: "#f7f9f8",
    theme_color: "#0f4c3a",
    lang: "ko",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
