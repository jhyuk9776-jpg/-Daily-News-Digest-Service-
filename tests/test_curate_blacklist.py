"""블랙리스트 기자가 대표로 안 뽑히는지 검증(D5: pool 선제거 → 대표 게이트 이동).

블랙리스트 기자 기사는 클러스터 멤버로는 남아 교차검증에 기여하되, 대표로는 제외된다.
(부실 기자라고 그 사건이 없던 게 아니므로 사건 증거로는 유효.)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402
import reporters  # noqa: E402


def _m(source, author, link):
    return {"source": source, "author": author, "link": link,
            "title": "같은 사건", "category": "경제"}


class BlacklistGateTest(unittest.TestCase):
    def _pick(self, cluster, blacklist):
        body = "본문 " * 100  # 유효 길이(300~1500)
        return curate.pick_representative(
            cluster, lambda link, title="": body,
            lambda title, b: {"total": 0.9}, {}, [], blacklist=blacklist)

    def test_blacklisted_not_representative(self):
        cluster = {"members": [_m("연합뉴스", "황철환 기자", "x"),
                               _m("한국경제", "김리안", "y")]}
        bl = {reporters.reporter_key("연합뉴스", "황철환 기자")}
        rep = self._pick(cluster, bl)
        self.assertEqual(rep["link"], "y")  # 블랙 아닌 멤버가 대표

    def test_blacklist_only_member_drops_cluster(self):
        cluster = {"members": [_m("연합뉴스", "황철환 기자", "x")]}
        bl = {reporters.reporter_key("연합뉴스", "황철환 기자")}
        self.assertIsNone(self._pick(cluster, bl))  # 유일 멤버 블랙 → 드롭

    def test_no_blacklist_passes(self):
        cluster = {"members": [_m("연합뉴스", "황철환 기자", "x")]}
        rep = self._pick(cluster, set())
        self.assertEqual(rep["link"], "x")

    def test_author_none_passes(self):
        cluster = {"members": [{"source": "연합뉴스", "link": "x",
                                "title": "무저자", "category": "경제"}]}
        rep = self._pick(cluster, {reporters.reporter_key("연합뉴스", "황철환")})
        self.assertEqual(rep["link"], "x")  # author 없으면 키 불일치 → 통과


if __name__ == "__main__":
    unittest.main()
