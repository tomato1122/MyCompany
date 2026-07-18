"""収集結果の保存(JSON / CSV)と既存データとのマージ。"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from .collector import filter_active
from .models import COUPON_FIELDS, Coupon, now_utc

logger = logging.getLogger(__name__)

JSON_FILENAME = "coupons.json"
CSV_FILENAME = "coupons.csv"


def load_existing(output_dir: Path) -> list[Coupon]:
    """既存の coupons.json を読み込む。無い・壊れている場合は空リスト。"""
    json_path = output_dir / JSON_FILENAME
    if not json_path.exists():
        return []
    try:
        with json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("coupons", data) if isinstance(data, dict) else data
        coupons = [Coupon.from_dict(r) for r in records if isinstance(r, dict)]
        logger.info("既存データを読み込み: %s (%d 件)", json_path, len(coupons))
        return coupons
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("既存データの読み込みに失敗したため無視します (%s): %s", json_path, exc)
        return []


def merge(existing: Iterable[Coupon], new: Iterable[Coupon]) -> list[Coupon]:
    """既存 + 新規をIDでマージし、期限切れを除去して返す。新規が既存を上書きする。"""
    merged: dict[str, Coupon] = {c.id: c for c in existing}
    added = updated = 0
    for coupon in new:
        if coupon.id in merged:
            updated += 1
        else:
            added += 1
        merged[coupon.id] = coupon
    active = filter_active(merged.values())
    removed = len(merged) - len(active)
    logger.info(
        "マージ結果: 新規 %d 件・更新 %d 件・期限切れ削除 %d 件 → 合計 %d 件",
        added, updated, removed, len(active),
    )
    # 期限が近い順(期限なしは末尾)、同順位はID順で安定ソート
    active.sort(key=lambda c: (c.expires_at is None, c.expires_at or c.fetched_at, c.id))
    return active


def save(coupons: list[Coupon], output_dir: Path) -> tuple[Path, Path]:
    """クーポン一覧を coupons.json / coupons.csv に書き出す。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / JSON_FILENAME
    payload = {
        "updated_at": now_utc().isoformat(),
        "count": len(coupons),
        "coupons": [c.to_dict() for c in coupons],
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    csv_path = output_dir / CSV_FILENAME
    # Excel での文字化け防止のため BOM 付き UTF-8 で出力
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COUPON_FIELDS)
        writer.writeheader()
        for coupon in coupons:
            writer.writerow(coupon.to_dict())

    logger.info("保存完了: %s / %s (%d 件)", json_path, csv_path, len(coupons))
    return json_path, csv_path


def merge_and_save(new_coupons: list[Coupon], output_dir: Path) -> list[Coupon]:
    """既存データとマージして保存し、保存後の全件を返す。"""
    existing = load_existing(output_dir)
    merged = merge(existing, new_coupons)
    save(merged, output_dir)
    return merged
