"""dry-run 모드가 scores/ 누적 상태를 건드리지 않는지 검증(오염 사고 재발 방지).

curate.main(dry_run=True)는 파이프라인을 전부 돌리되 상태 영속화(가중치·주제·평판·
기자스트라이크)만 생략해야 한다. selected/ 는 gitignore 산출물이라 dry-run에서도 기록.
네트워크(extract_body)와 실제 파일쓰기는 mock으로 차단."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402


def _raw():
    arts = [
        {"title": "코스피 3000 돌파", "source": "한국경제", "link": "a",
         "category": "경제", "summary": "", "published_iso": "", "author": ""},
        {"title": "코스피 강세 지속", "source": "매일경제", "link": "b",
         "category": "경제", "summary": "", "published_iso": "", "author": ""},
    ]
    return {"date": "2099-01-01", "articles": arts}


class DryRunTest(unittest.TestCase):
    def _run(self, dry_run):
        """persist 함수들을 spy로 갈아끼우고 main 실행 → (호출된 spy 이름 집합) 반환."""
        import core_words
        import objectivity
        import reporters
        with patch("curate.load_raw", return_value=_raw()), \
             patch("extract.extract_body", return_value="본문 " * 200), \
             patch("curate.save") as m_save, \
             patch.object(core_words, "save_weights") as m_w, \
             patch.object(core_words, "record_topics") as m_t, \
             patch.object(reporters, "save") as m_r, \
             patch.object(objectivity, "save_store") as m_s:
            rc = curate.main("2099-01-01", dry_run=dry_run)
        self.assertEqual(rc, 0)
        return {
            "save_weights": m_w.called, "record_topics": m_t.called,
            "reporters_save": m_r.called, "save_store": m_s.called,
            "selected_save": m_save.called,
        }

    def test_dry_run_skips_state_writes(self):
        c = self._run(dry_run=True)
        self.assertFalse(c["save_weights"], "dry-run이 가중치를 저장하면 안 됨")
        self.assertFalse(c["record_topics"], "dry-run이 주제를 저장하면 안 됨")
        self.assertFalse(c["reporters_save"], "dry-run이 기자 스트라이크를 저장하면 안 됨")
        self.assertFalse(c["save_store"], "dry-run이 media.json(평판)을 저장하면 안 됨")
        self.assertTrue(c["selected_save"], "selected/ 는 dry-run에서도 기록해야 함")

    def test_normal_run_persists_state(self):
        c = self._run(dry_run=False)
        self.assertTrue(c["save_weights"])
        self.assertTrue(c["save_store"])
        self.assertTrue(c["selected_save"])


if __name__ == "__main__":
    unittest.main()
