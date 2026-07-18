"""CLI エントリポイント: python -m coupon_collector"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .collector import collect
from .sources import ALL_SOURCES, create_sources
from .storage import merge_and_save


def build_parser() -> argparse.ArgumentParser:
    source_names = [cls().name for cls in ALL_SOURCES]
    parser = argparse.ArgumentParser(
        prog="python -m coupon_collector",
        description="国内クーポン情報を収集して JSON/CSV に蓄積するツール",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=source_names,
        metavar="NAME",
        help=f"実行するソース名(複数指定可)。省略時は全ソース。候補: {', '.join(source_names)}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="出力先ディレクトリ(デフォルト: data/)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="デバッグログを出力")
    parser.add_argument("--version", action="version", version=f"coupon-collector {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logger = logging.getLogger("coupon_collector")

    try:
        sources = create_sources(args.source)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    coupons = collect(sources)
    saved = merge_and_save(coupons, args.output_dir)
    logger.info(
        "完了: 今回 %d 件収集、保存後の全件数 %d 件 (出力先: %s)",
        len(coupons), len(saved), args.output_dir.resolve(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
