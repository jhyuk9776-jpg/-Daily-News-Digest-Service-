import Link from "next/link";

export default function Footer() {
  return (
    <footer className="site-footer">
      <nav>
        <Link href="/">오늘의 요약</Link>
        <Link href="/about">소개</Link>
        <Link href="/privacy">개인정보</Link>
        <Link href="/terms">이용약관</Link>
      </nav>
      <p>개인용·비상업 뉴스 다이제스트 · 각 기사의 저작권은 해당 언론사에 있습니다.</p>
    </footer>
  );
}
