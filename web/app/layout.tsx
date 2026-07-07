export const metadata = {
  title: "오늘의 뉴스 다이제스트",
  description: "사실 중심 뉴스 요약",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
