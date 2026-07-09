"use client";
import { useEffect } from "react";

// 오프라인 지원용 서비스워커 등록(설치는 브라우저가 처리). 실패해도 앱은 정상 동작.
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);
  return null;
}
