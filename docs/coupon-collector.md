# coupon-collector 利用・運用ガイド

国内のクーポン情報を公式 API から収集し、`data/coupons.json` / `data/coupons.csv` に蓄積する Python ツールです。

- **対象読者**: ツールを手元で実行したい利用者、および定期実行(GitHub Actions)を管理する運用者
- **バージョン**: coupon-collector 0.1.0(`coupon_collector/__init__.py` の `__version__`)
- **動作確認環境**: Python 3.11(コードは `from __future__ import annotations` と `X | None` 型注釈を使用しており、Python 3.10 以上を推奨。CI での正式なサポート範囲は要確認)

## 目次

1. [概要とアーキテクチャ](#概要とアーキテクチャ)
2. [セットアップ](#セットアップ)
3. [使い方](#使い方)
4. [出力ファイル形式](#出力ファイル形式)
5. [定期実行(GitHub Actions)](#定期実行github-actions)
6. [新しいソースの追加方法](#新しいソースの追加方法)
7. [利用上の注意(API 利用規約・クレジット表記・レートリミット)](#利用上の注意api-利用規約クレジット表記レートリミット)
8. [トラブルシューティング](#トラブルシューティング)

---

## 概要とアーキテクチャ

### 処理の流れ

```
python -m coupon_collector
        │
        ▼
 sources(プラグイン群)──► collector.collect() ──► storage.merge_and_save()
   demo / hotpepper /        重複・期限切れを除外       既存 data/coupons.json と
   rakuten / (追加可能)      ソース間に1秒ウェイト      IDでマージし期限切れを削除
                                                        → coupons.json / coupons.csv
```

### モジュール構成

| ファイル | 役割 |
| --- | --- |
| `coupon_collector/__main__.py` | CLI エントリポイント(`python -m coupon_collector`) |
| `coupon_collector/models.py` | `Coupon` データクラス、ID 生成(`make_coupon_id`)、日時の正規化 |
| `coupon_collector/collector.py` | 全ソースの実行、重複・期限切れの除外、ソース間ウェイト(1 秒) |
| `coupon_collector/storage.py` | 既存データとのマージ、`coupons.json` / `coupons.csv` の書き出し |
| `coupon_collector/http.py` | HTTP 共通処理(タイムアウト 10 秒、リトライ最大 2 回、User-Agent 明示) |
| `coupon_collector/sources/base.py` | プラグインの抽象基底クラス `CouponSource` |
| `coupon_collector/sources/__init__.py` | ソースの登録簿 `ALL_SOURCES` と生成関数 `create_sources()` |

### ソースのプラグイン構造

クーポンの取得元は「ソース」としてプラグイン化されています。各ソースは抽象基底クラス
`CouponSource`(`coupon_collector/sources/base.py`)を継承し、次の 3 つを実装・設定します。

- `name` プロパティ — CLI の `--source` で指定する識別名
- `fetch()` — クーポンを取得して `list[Coupon]` を返す(ネットワークエラー等は例外を送出してよい)
- `is_configured()`(任意)— API キー等が未設定なら `False` を返す。`False` のソースはエラーにならず**スキップ**される

登録済みソース(`coupon_collector/sources/__init__.py` の `ALL_SOURCES`、実行順):

| ソース名 | 取得元 | 必要な環境変数 | 備考 |
| --- | --- | --- | --- |
| `demo` | 静的サンプル(4 件、うち 1 件は期限切れ) | なし | API キーなしで動作確認するためのソース |
| `hotpepper` | ホットペッパーグルメ API(グルメサーチ)のクーポン付き店舗 | `HOTPEPPER_API_KEY`(必須)、`HOTPEPPER_LARGE_AREA`(任意、デフォルト `Z011`=東京) | 1 回の実行で最大 50 件取得 |
| `rakuten` | 楽天商品検索 API(Ichiba Item Search)のクーポン/セール対象商品 | `RAKUTEN_APP_ID`(必須)、`RAKUTEN_KEYWORD`(任意、デフォルト「クーポン」) | 1 回の実行で最大 30 件取得 |

コレクタ(`collector.collect()`)はソースを順に実行し、

- `is_configured()` が `False` のソースはログを残してスキップ
- `fetch()` が例外を投げたソースもスキップし、**他のソースは続行**
- 2 つ目以降のソース実行前に 1 秒のウェイト(API 提供元への負荷配慮)
- 期限切れ(`expires_at` が過去)と ID 重複を除外

します。

## セットアップ

### 1. Python 環境の準備

Python 3.11 で動作確認しています。仮想環境の利用を推奨します。

```console
$ cd MyCompany
$ python -m venv .venv
$ source .venv/bin/activate
$ pip install -r requirements.txt
```

依存パッケージは `requests` のみです(`requirements.txt`: `requests>=2.31,<3`)。

### 2. API キーの取得(実データを収集する場合)

`demo` ソースだけを使う場合は不要です。実 API から収集する場合は以下で無料登録し、キーを取得してください。

| ソース | 登録先 | 取得するもの | 設定する環境変数 |
| --- | --- | --- | --- |
| `hotpepper` | [リクルート Web サービス](https://webservice.recruit.co.jp/) | API キー | `HOTPEPPER_API_KEY` |
| `rakuten` | [楽天ウェブサービス](https://webservice.rakuten.co.jp/) | アプリ ID(applicationId) | `RAKUTEN_APP_ID` |

```console
$ export HOTPEPPER_API_KEY="取得したAPIキー"
$ export RAKUTEN_APP_ID="取得したアプリID"
```

> 各サービスでの登録から GitHub Secrets への設定までの詳しい手順は **[docs/api-keys-setup.md](api-keys-setup.md)** を参照してください。

環境変数が未設定でもエラーにはならず、該当ソースがスキップされるだけです(ログに「APIキー等が未設定のためスキップします」と出ます)。

### 3. 動作確認

```console
$ python -m coupon_collector --version
coupon-collector 0.1.0
```

## 使い方

### コマンドラインオプション

```console
$ python -m coupon_collector --help
usage: python -m coupon_collector [-h] [--source NAME]
                                  [--output-dir OUTPUT_DIR] [--verbose]
                                  [--version]

国内クーポン情報を収集して JSON/CSV に蓄積するツール

options:
  -h, --help            show this help message and exit
  --source NAME         実行するソース名(複数指定可)。省略時は全ソース。候補: demo, hotpepper, rakuten
  --output-dir OUTPUT_DIR
                        出力先ディレクトリ(デフォルト: data/)
  --verbose, -v         デバッグログを出力
  --version             show program's version number and exit
```

### 例 1: demo ソースだけを実行(API キー不要)

まずはキーなしで全パイプラインの動作を確認できます。以下は実際の実行結果です(タイムスタンプと出力先パスは環境により異なります)。

```console
$ python -m coupon_collector --source demo
2026-07-18 15:27:07,358 INFO    coupon_collector.collector: ソース 'demo' から取得を開始
2026-07-18 15:27:07,358 INFO    coupon_collector.sources.demo: demo: サンプルクーポン 4 件を生成(うち1件は期限切れ)
2026-07-18 15:27:07,358 INFO    coupon_collector.collector: ソース 'demo': 3 件追加 (重複 0 件・期限切れ 1 件を除外)
2026-07-18 15:27:07,358 INFO    coupon_collector.collector: 収集完了: 合計 3 件
2026-07-18 15:27:07,358 INFO    coupon_collector.storage: マージ結果: 新規 3 件・更新 0 件・期限切れ削除 0 件 → 合計 3 件
2026-07-18 15:27:07,359 INFO    coupon_collector.storage: 保存完了: data/coupons.json / data/coupons.csv (3 件)
2026-07-18 15:27:07,360 INFO    coupon_collector: 完了: 今回 3 件収集、保存後の全件数 3 件 (出力先: /home/user/MyCompany/data)
```

demo ソースは意図的に期限切れサンプルを 1 件含んでおり、「4 件生成 → 3 件保存」となるのが正常です。

### 例 2: 全ソースを実行(省略時のデフォルト)

API キーを設定していない状態で実行すると、該当ソースはスキップされます。以下は実際の実行結果です。

```console
$ python -m coupon_collector
2026-07-18 15:27:18,154 INFO    coupon_collector.collector: ソース 'demo' から取得を開始
2026-07-18 15:27:18,154 INFO    coupon_collector.sources.demo: demo: サンプルクーポン 4 件を生成(うち1件は期限切れ)
2026-07-18 15:27:18,154 INFO    coupon_collector.collector: ソース 'demo': 3 件追加 (重複 0 件・期限切れ 1 件を除外)
2026-07-18 15:27:18,154 INFO    coupon_collector.collector: ソース 'hotpepper' はAPIキー等が未設定のためスキップします
2026-07-18 15:27:18,154 INFO    coupon_collector.collector: ソース 'rakuten' はAPIキー等が未設定のためスキップします
2026-07-18 15:27:18,154 INFO    coupon_collector.collector: 収集完了: 合計 3 件
2026-07-18 15:27:18,155 INFO    coupon_collector.storage: 既存データを読み込み: data/coupons.json (3 件)
2026-07-18 15:27:18,155 INFO    coupon_collector.storage: マージ結果: 新規 0 件・更新 3 件・期限切れ削除 0 件 → 合計 3 件
2026-07-18 15:27:18,156 INFO    coupon_collector.storage: 保存完了: data/coupons.json / data/coupons.csv (3 件)
2026-07-18 15:27:18,156 INFO    coupon_collector: 完了: 今回 3 件収集、保存後の全件数 3 件 (出力先: /home/user/MyCompany/data)
```

2 回目以降の実行では既存の `coupons.json` が読み込まれ、同一 ID のクーポンは新しいデータで**上書き**(更新)されます。

### 例 3: ソースと出力先を指定

```console
$ python -m coupon_collector --source hotpepper --source rakuten --output-dir /path/to/output
```

- `--source` は複数指定でき、指定した順に実行されます
- 未知のソース名を指定すると終了コード 2 でエラーになります(例: `未知のソース名: foo (利用可能: demo, hotpepper, rakuten)`)
- `--verbose` (`-v`) で DEBUG レベルのログ(HTTP リトライの詳細など)が出ます

### 検索条件のカスタマイズ(環境変数)

| 環境変数 | 対象ソース | 意味 | デフォルト |
| --- | --- | --- | --- |
| `HOTPEPPER_LARGE_AREA` | hotpepper | 検索対象の大エリアコード | `Z011`(東京) |
| `RAKUTEN_KEYWORD` | rakuten | 商品検索キーワード | `クーポン` |

エリアコードの一覧はホットペッパーグルメ API のマスタ API(公式リファレンス参照)で確認できます。

## 出力ファイル形式

出力先ディレクトリ(デフォルト `data/`)に 2 ファイルが書き出されます。どちらも**毎回全件を書き直す**方式です(追記ではありません)。

### data/coupons.json

UTF-8・インデント 2 の JSON。トップレベルにメタ情報を持ち、`coupons` 配列に全件が入ります。
並び順は「有効期限が近い順(期限なしは末尾)、同順位は ID 順」です。

実際の出力例(demo ソース実行後):

```json
{
  "updated_at": "2026-07-18T15:27:07.358808+00:00",
  "count": 3,
  "coupons": [
    {
      "id": "demo-e062cf1fdea0e873",
      "source": "demo",
      "title": "ドリンク1杯無料",
      "description": "デモ用サンプルクーポン。ケーキセット注文で適用。",
      "shop_name": "デモカフェ 渋谷店",
      "discount": "ドリンク無料",
      "url": "https://example.com/coupons/cafe-drink-free",
      "expires_at": "2026-07-26T00:27:07.358264+09:00",
      "fetched_at": "2026-07-18T15:27:07.358466+00:00"
    }
  ]
}
```

各フィールドの意味:

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `id` | string | `<ソース名>-<SHA-256先頭16桁>`。ソース名とソース内固有キーから決定的に生成され、マージの重複判定キーになる |
| `source` | string | 取得元ソース名(`demo` / `hotpepper` / `rakuten` など) |
| `title` | string | クーポン・商品のタイトル |
| `description` | string | 説明(rakuten は商品説明の先頭 200 文字) |
| `shop_name` | string | 店舗名・ショップ名 |
| `discount` | string | 割引内容の表記(例: `100円引き`、`ポイント2倍`。取れない場合は空文字) |
| `url` | string | クーポン・商品ページの URL |
| `expires_at` | string \| null | 有効期限(ISO 8601、JST オフセット付き)。`null` は期限情報なし=有効扱い。hotpepper / rakuten は API が個別期限を返さないため常に `null` |
| `fetched_at` | string | 取得日時(ISO 8601、UTC) |

### data/coupons.csv

同じ内容の CSV(列順: `id, source, title, description, shop_name, discount, url, expires_at, fetched_at`)。
Excel で開いたときの文字化け防止のため **BOM 付き UTF-8**(`utf-8-sig`)で出力されます。`expires_at` が `null` の行は空欄になります。

```csv
id,source,title,description,shop_name,discount,url,expires_at,fetched_at
demo-e062cf1fdea0e873,demo,ドリンク1杯無料,デモ用サンプルクーポン。ケーキセット注文で適用。,デモカフェ 渋谷店,ドリンク無料,https://example.com/coupons/cafe-drink-free,2026-07-26T00:27:07.358264+09:00,2026-07-18T15:27:07.358466+00:00
```

### マージの仕様

- 実行のたびに既存の `coupons.json` を読み込み、ID でマージ(**新規データが既存を上書き**)
- マージ後に期限切れ(`expires_at` が現在時刻より過去)を削除
- 既存 JSON が存在しない・壊れている場合は警告ログを出して空データとして扱う(実行は失敗しない)

## 定期実行(GitHub Actions)

> **注意**: ワークフローとテスト一式は別ブランチで追加予定であり、このブランチのリポジトリにはまだ含まれていません。ワークフローのファイル名・ジョブ構成の詳細はマージ後に要確認です。

計画されている構成:

- **スケジュール**: 毎日 JST 06:00 に実行(GitHub Actions の cron は UTC 指定のため `0 21 * * *` 相当)
- **処理内容**: `python -m coupon_collector` を実行し、更新された `data/coupons.json` / `data/coupons.csv` をリポジトリに自動コミット
- **テスト**: pytest によるテスト 105 件も同ブランチで追加予定(`pytest` で実行)

### Secrets の設定手順(運用者向け)

API キーはリポジトリに直接書かず、GitHub Actions の Secrets に登録します。

1. GitHub のリポジトリページで **Settings → Secrets and variables → Actions** を開く
2. **New repository secret** をクリックし、以下の 2 件を登録する

   | Name | Value |
   | --- | --- |
   | `HOTPEPPER_API_KEY` | リクルート Web サービスで取得した API キー |
   | `RAKUTEN_APP_ID` | 楽天ウェブサービスで取得したアプリ ID |

3. ワークフロー側では Secrets が同名の環境変数としてジョブに渡される想定(具体的な受け渡し方はワークフローのマージ後に要確認)

Secrets が未設定でもワークフロー自体は失敗せず、該当ソースがスキップされて demo(および設定済みソース)のみが収集されます。

## 新しいソースの追加方法

`CouponSource` を継承したクラスを 1 つ書き、登録簿に追加するだけです。

### 手順

1. `coupon_collector/sources/` に新しいモジュール(例: `example.py`)を作成し、`CouponSource` を継承する
2. API キー等が必要なら `is_configured()` をオーバーライドする(未設定時はスキップされる)
3. `coupon_collector/sources/__init__.py` の `ALL_SOURCES` にクラスを追加する

### コード例: `coupon_collector/sources/example.py`

```python
"""新しいクーポン提供元の例。"""

from __future__ import annotations

import os

from .. import http
from ..models import Coupon, make_coupon_id
from .base import CouponSource


class ExampleSource(CouponSource):
    """新しいクーポン提供元の例。"""

    @property
    def name(self) -> str:
        return "example"  # CLI の --source で指定する名前

    def is_configured(self) -> bool:
        # APIキーが必要な場合は環境変数の有無を返す(未設定ならスキップされる)
        return bool(os.environ.get("EXAMPLE_API_KEY"))

    def fetch(self) -> list[Coupon]:
        # 共通の http.get_json() を使うとタイムアウト・リトライ・User-Agent が統一される
        data = http.get_json(
            "https://api.example.com/v1/coupons",
            params={"key": os.environ["EXAMPLE_API_KEY"], "limit": 50},
        )
        coupons: list[Coupon] = []
        for item in data.get("coupons", []):
            coupons.append(
                Coupon(
                    id=make_coupon_id(self.name, item["code"]),  # ソース内で安定した固有キーを渡す
                    source=self.name,
                    title=item["title"],
                    description=item.get("description", ""),
                    shop_name=item.get("shop", ""),
                    discount=item.get("discount", ""),
                    url=item.get("url", ""),
                    expires_at=item.get("expires_at"),  # ISO 8601 文字列のままでよい(自動で正規化される)
                )
            )
        return coupons
```

### 登録: `coupon_collector/sources/__init__.py`

```python
from .example import ExampleSource

ALL_SOURCES: list[type[CouponSource]] = [
    DemoSource,
    HotpepperSource,
    RakutenSource,
    ExampleSource,  # ← 追加
]
```

これだけで `python -m coupon_collector --source example` が使えるようになり、`--help` の候補にも自動で表示されます。

### 実装時のポイント

- **ID は安定させる**: `make_coupon_id(self.name, 固有キー)` に、API が返す不変の ID(店舗 ID・商品コード等)を渡してください。実行のたびに変わる値を使うと、マージ時に重複が蓄積します
- **`expires_at` は naive でも文字列でもよい**: `Coupon` の `__post_init__` が正規化します。タイムゾーンなしの datetime は **JST とみなされます**
- **HTTP は `http.get_json()` を使う**: タイムアウト 10 秒・最大 2 回リトライ・User-Agent 明示が共通化されています。公式 API 以外へのアクセス(robots.txt を回避するようなスクレイピング)は行わない方針です
- **例外はそのまま投げてよい**: コレクタが捕捉してそのソースだけスキップし、他のソースは続行します

## 利用上の注意(API 利用規約・クレジット表記・レートリミット)

- **各 API の利用規約を遵守してください。** 本ツールはリクルート Web サービスおよび楽天ウェブサービスの公式 API のみを利用します。取得したデータの利用範囲・再配布の可否は各サービスの利用規約に従ってください。
- **クレジット表記の義務**: 取得データを Web サイト等で公開利用する場合、リクルート Web サービス・楽天ウェブサービスのいずれも所定のクレジット(帰属)表記が義務付けられています。表記の文言・形式は各サービスの公式ページ(https://webservice.recruit.co.jp/ / https://webservice.rakuten.co.jp/)で最新の規約を確認してください(具体的な表記要件はコードからは確認できないため要確認)。
- **レートリミットへの配慮**: 本ツールはソース間に 1 秒のウェイトを入れ、1 回の実行での取得件数を hotpepper 50 件・rakuten 30 件に抑え、HTTP リトライも最大 2 回(間隔を空けて)に制限しています。短時間に手動実行を繰り返す、取得件数の定数(`FETCH_COUNT`)をむやみに増やす、といった各 API のレートリミットを圧迫する使い方は避けてください。各サービスの具体的なリクエスト上限は公式ドキュメントを確認してください。
- **API キーの管理**: キーをコードやコミットに含めないでください。ローカルでは環境変数、GitHub Actions では Secrets を使います。

## トラブルシューティング

| 症状 | 原因と対処 |
| --- | --- |
| `ソース 'hotpepper' はAPIキー等が未設定のためスキップします` | 環境変数 `HOTPEPPER_API_KEY`(rakuten の場合 `RAKUTEN_APP_ID`)が未設定。エラーではなく仕様。実データを取りたい場合はキーを設定する |
| `未知のソース名: ...`(終了コード 2) | `--source` の指定ミス。`--help` で候補を確認する |
| `ホットペッパーAPIエラー: ...` / `楽天APIエラー: ...` | API がエラーを返した(キー不正・パラメータ不正など)。キーの値と各 API の稼働状況を確認する。該当ソースはスキップされ、他ソースは続行する |
| `既存データの読み込みに失敗したため無視します` | `coupons.json` が壊れている。警告のみで実行は続き、当回の収集結果で新しく書き直される |
| HTTP エラーでリトライを繰り返す | ネットワークまたは API 側の問題。最大 3 試行(初回+リトライ 2 回)後に該当ソースはスキップされる。`--verbose` で詳細を確認する |
