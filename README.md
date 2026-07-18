# MyCompany

社内ツール・実験プロジェクトのモノレポです。現在の主なプロジェクトは **coupon-collector**
(国内クーポン情報を公式 API から収集して `data/coupons.json` / `data/coupons.csv` に蓄積する Python ツール)です。

## coupon-collector クイックスタート

API キーなしでも `demo` ソースで動作を確認できます。

```console
# 1. 依存関係をインストール(Python 3.11 で動作確認済み)
$ pip install -r requirements.txt

# 2. demo ソースで実行(APIキー不要)
$ python -m coupon_collector --source demo

# 3. 出力を確認
$ cat data/coupons.json
```

実データを収集する場合は、[リクルート Web サービス](https://webservice.recruit.co.jp/)と
[楽天ウェブサービス](https://webservice.rakuten.co.jp/)で無料登録し、
環境変数 `HOTPEPPER_API_KEY` / `RAKUTEN_APP_ID` を設定してから `python -m coupon_collector` を実行してください。

詳細(アーキテクチャ、出力形式、GitHub Actions での定期実行、新しいソースの追加方法、API 利用上の注意)は
**[docs/coupon-collector.md](docs/coupon-collector.md)** を参照してください。

## リポジトリ構成

```
coupon_collector/   # 収集ツール本体(sources/ 配下がプラグイン)
docs/               # ドキュメント
data/               # 収集結果(定期実行で自動コミット予定)
tests/              # pytest テスト(別ブランチで追加予定)
```

## 開発体制について

このリポジトリでは、部署ごとのサブエージェント(開発部・ドキュメント部など)が分担して開発・文書化を行う体制を採っています。体制の詳細は `CLAUDE.md` を参照してください。
