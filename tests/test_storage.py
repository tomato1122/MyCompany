"""storage.py のユニットテスト(マージ・JSON/CSV 出力)。"""

from __future__ import annotations

import csv
import json
from datetime import timedelta

from coupon_collector import storage
from coupon_collector.models import COUPON_FIELDS, Coupon
from tests.conftest import FIXED_NOW, make_coupon


def _write_json(output_dir, payload):
    path = output_dir / storage.JSON_FILENAME
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _freeze_now(monkeypatch):
    """storage / collector が参照する now_utc を FIXED_NOW に固定する。"""
    monkeypatch.setattr("coupon_collector.storage.now_utc", lambda: FIXED_NOW)
    monkeypatch.setattr("coupon_collector.collector.now_utc", lambda: FIXED_NOW)


class TestLoadExisting:
    def test_missing_file_returns_empty(self, tmp_path):
        assert storage.load_existing(tmp_path) == []

    def test_corrupt_json_returns_empty(self, tmp_path):
        (tmp_path / storage.JSON_FILENAME).write_text("{not json", encoding="utf-8")
        assert storage.load_existing(tmp_path) == []

    def test_reads_wrapped_payload(self, tmp_path):
        c = make_coupon(fetched_at=FIXED_NOW)
        _write_json(tmp_path, {"updated_at": "x", "count": 1, "coupons": [c.to_dict()]})
        loaded = storage.load_existing(tmp_path)
        assert loaded == [c]

    def test_reads_bare_list_format(self, tmp_path):
        c = make_coupon(fetched_at=FIXED_NOW)
        _write_json(tmp_path, [c.to_dict()])
        assert storage.load_existing(tmp_path) == [c]

    def test_non_dict_records_are_skipped(self, tmp_path):
        c = make_coupon(fetched_at=FIXED_NOW)
        _write_json(tmp_path, {"coupons": [c.to_dict(), "junk", 42, None]})
        assert storage.load_existing(tmp_path) == [c]

    def test_record_missing_required_field_drops_all(self, tmp_path):
        # 現仕様: 必須キー欠落レコードが1件でもあると TypeError → 全体を捨てて []
        good = make_coupon(fetched_at=FIXED_NOW)
        _write_json(tmp_path, {"coupons": [good.to_dict(), {"title": "idなし"}]})
        assert storage.load_existing(tmp_path) == []


class TestMerge:
    def test_new_coupons_are_added(self):
        a = make_coupon(id="a", expires_at=FIXED_NOW + timedelta(days=400))
        b = make_coupon(id="b", expires_at=FIXED_NOW + timedelta(days=400))
        merged = storage.merge([a], [b])
        assert {c.id for c in merged} == {"a", "b"}

    def test_same_id_new_overwrites_existing(self):
        far_future = FIXED_NOW + timedelta(days=400)
        old = make_coupon(id="a", title="旧タイトル", expires_at=far_future)
        new = make_coupon(id="a", title="新タイトル", expires_at=far_future)
        merged = storage.merge([old], [new])
        assert len(merged) == 1
        assert merged[0].title == "新タイトル"

    def test_expired_existing_removed(self, monkeypatch):
        _freeze_now(monkeypatch)
        expired = make_coupon(id="old", expires_at=FIXED_NOW - timedelta(days=1))
        fresh = make_coupon(id="new", expires_at=FIXED_NOW + timedelta(days=1))
        merged = storage.merge([expired], [fresh])
        assert [c.id for c in merged] == ["new"]

    def test_expired_new_coupon_also_removed(self, monkeypatch):
        _freeze_now(monkeypatch)
        expired_new = make_coupon(id="x", expires_at=FIXED_NOW - timedelta(hours=1))
        assert storage.merge([], [expired_new]) == []

    def test_empty_inputs(self):
        assert storage.merge([], []) == []

    def test_sorted_by_expiry_none_last_ties_by_id(self, monkeypatch):
        _freeze_now(monkeypatch)
        soon = make_coupon(id="soon", expires_at=FIXED_NOW + timedelta(days=1))
        later = make_coupon(id="later", expires_at=FIXED_NOW + timedelta(days=10))
        no_exp_b = make_coupon(id="b-none", expires_at=None, fetched_at=FIXED_NOW)
        no_exp_a = make_coupon(id="a-none", expires_at=None, fetched_at=FIXED_NOW)
        merged = storage.merge([no_exp_b, later], [soon, no_exp_a])
        assert [c.id for c in merged] == ["soon", "later", "a-none", "b-none"]


class TestSave:
    def _coupons(self):
        return [
            Coupon(
                id="demo-1",
                source="demo",
                title="日本語タイトル,カンマ入り",
                shop_name="店舗",
                expires_at=FIXED_NOW + timedelta(days=1),
                fetched_at=FIXED_NOW,
            ),
            make_coupon(id="demo-2", expires_at=None, fetched_at=FIXED_NOW),
        ]

    def test_creates_output_dir_and_both_files(self, tmp_path):
        out = tmp_path / "nested" / "data"
        json_path, csv_path = storage.save(self._coupons(), out)
        assert json_path.exists() and csv_path.exists()

    def test_json_structure(self, tmp_path, monkeypatch):
        _freeze_now(monkeypatch)
        storage.save(self._coupons(), tmp_path)
        data = json.loads((tmp_path / storage.JSON_FILENAME).read_text(encoding="utf-8"))
        assert data["updated_at"] == FIXED_NOW.isoformat()
        assert data["count"] == 2
        assert len(data["coupons"]) == 2
        assert data["coupons"][0]["id"] == "demo-1"
        assert data["coupons"][0]["expires_at"] == (FIXED_NOW + timedelta(days=1)).isoformat()
        assert data["coupons"][1]["expires_at"] is None

    def test_json_is_human_readable_utf8(self, tmp_path):
        storage.save(self._coupons(), tmp_path)
        raw = (tmp_path / storage.JSON_FILENAME).read_text(encoding="utf-8")
        assert "日本語タイトル" in raw  # ensure_ascii=False
        assert raw.endswith("\n")

    def test_csv_has_utf8_bom_and_header(self, tmp_path):
        storage.save(self._coupons(), tmp_path)
        raw = (tmp_path / storage.CSV_FILENAME).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")  # Excel 向け BOM
        with (tmp_path / storage.CSV_FILENAME).open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        assert rows[0] == COUPON_FIELDS
        assert len(rows) == 3  # ヘッダ + 2件

    def test_csv_roundtrip_of_values(self, tmp_path):
        storage.save(self._coupons(), tmp_path)
        with (tmp_path / storage.CSV_FILENAME).open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["title"] == "日本語タイトル,カンマ入り"
        assert rows[0]["expires_at"] == (FIXED_NOW + timedelta(days=1)).isoformat()
        assert rows[1]["expires_at"] == ""  # None は空文字として出力

    def test_save_empty_list(self, tmp_path):
        storage.save([], tmp_path)
        data = json.loads((tmp_path / storage.JSON_FILENAME).read_text(encoding="utf-8"))
        assert data["count"] == 0 and data["coupons"] == []

    def test_saved_json_can_be_loaded_back(self, tmp_path):
        coupons = self._coupons()
        storage.save(coupons, tmp_path)
        assert storage.load_existing(tmp_path) == coupons


class TestMergeAndSave:
    def test_full_cycle_add_update_expire(self, tmp_path, monkeypatch):
        _freeze_now(monkeypatch)
        # 1回目: 有効2件 + 期限切れになる予定の1件を保存
        first = [
            make_coupon(id="keep", title="残る", expires_at=FIXED_NOW + timedelta(days=30)),
            make_coupon(id="update-me", title="旧", expires_at=FIXED_NOW + timedelta(days=30)),
            make_coupon(id="expired", title="切れる", expires_at=FIXED_NOW - timedelta(days=1)),
        ]
        # merge 時点の期限切れ除去があるため、期限切れ分は最初から保存されない
        saved1 = storage.merge_and_save(first, tmp_path)
        assert {c.id for c in saved1} == {"keep", "update-me"}

        # 2回目: 更新1件 + 新規1件
        second = [
            make_coupon(id="update-me", title="新", expires_at=FIXED_NOW + timedelta(days=60)),
            make_coupon(id="brand-new", title="新規", expires_at=FIXED_NOW + timedelta(days=5)),
        ]
        saved2 = storage.merge_and_save(second, tmp_path)
        assert {c.id for c in saved2} == {"keep", "update-me", "brand-new"}
        by_id = {c.id: c for c in saved2}
        assert by_id["update-me"].title == "新"

        # ファイル内容も一致
        data = json.loads((tmp_path / storage.JSON_FILENAME).read_text(encoding="utf-8"))
        assert data["count"] == 3
