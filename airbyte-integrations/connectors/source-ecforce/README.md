# ecforce ソースコネクタ

このリポジトリは、日本のECプラットフォーム「ecforce」用のAirbyteソースコネクタです。Pythonで実装されており、ecforce API v2からデータを取得します。

## 概要

ecforceは、D2C（Direct to Consumer）ブランド向けの高機能ECプラットフォームです。このコネクタを使用することで、ecforceのデータをAirbyteを通じて様々なデータウェアハウスやデータベースに同期できます。

## 主な機能

### 現在サポートしているストリーム

1. **Customers（顧客）**
   - 顧客の基本情報（会員番号、メールアドレス、会員ランクなど）
   - 購入履歴の集計情報（購入回数、購入総額、初回/最終購入日）
   - ポイント情報
   - 会員ステータス
   - カスタムラベル

2. **Customer Notes（顧客メモ）**
   - 顧客に関連付けられたメモ
   - 対応履歴やカスタマーサポートの記録
   - 親ストリーム（Customers）に依存

## 技術的特徴

### 増分同期（Incremental Sync）

- `updated_at`フィールドを使用した増分同期をサポート
- 月次スライスによる効率的なデータ取得
- 大量のデータでも安定した同期が可能

### パフォーマンス最適化

- `max_concurrent_streams = 1`による順次実行（API負荷軽減）
- 親ストリームのキャッシュ無効化によるメモリ使用量削減
- 月次スライスで大量データを分割処理

### レート制限対策

- APIリクエスト間の待機時間を設定可能（`request_interval`パラメータ）
- 429エラー（Too Many Requests）の自動リトライ
- 指数バックオフによる再試行メカニズム

### GCS（Google Cloud Storage）統合

- 大規模なデータセット用のキャッシュ機能
- 親ストリームのデータをGCSに保存し、子ストリームが効率的にアクセス
- Customer NotesストリームがCustomersデータを再取得せずに処理可能

### データ変換

- ecforceの日付形式（YYYY/MM/DD）をISO 8601形式に自動変換
- BigQueryなどのデータウェアハウスとの互換性を確保
- 不要なフィールドの自動除去

## 設定パラメータ

### 必須パラメータ

- **domain**: ecforceショップのドメイン（例：`myshop.ec-force.com`）
- **api_token**: ecforce API v2の認証トークン
- **company_name**: 会社名（GCSでのデータ整理に使用、英数字とハイフンのみ）
- **gcs_bucket**: GCSバケット名（親子ストリーム同期に必要）
- **gcs_service_account_key**: GCSサービスアカウントのJSONキー

### オプションパラメータ

- **start_date**: データ同期の開始日（デフォルト：2年前）
- **end_date**: データ同期の終了日（デフォルト：日本時間の昨日）
- **include_notes**: 顧客メモを含めるかどうか（デフォルト：false）
- **request_interval**: APIリクエスト間の待機秒数（デフォルト：1秒、最大：120秒）

## 使用方法

### 1. 前提条件

- ecforce API v2へのアクセス権限
- APIトークンの取得
- Google Cloud Storageのバケット（親子ストリーム使用時）
- Python 3.12以上

### 2. ローカルでのテスト

```bash
# 依存関係のインストール
poetry install

# コネクタの仕様確認
poetry run python main.py spec

# 接続テスト
poetry run python main.py check --config secrets/config.json

# ストリームの検出
poetry run python main.py discover --config secrets/config.json

# データの読み取り
poetry run python main.py read --config secrets/config.json --catalog configured_catalog.json
```

### 3. Dockerでの実行

```bash
# Airbyte CDKを使用したイメージのビルド（推奨）
airbyte-cdk image build --tag 0.1.1

# ビルドされたイメージで実行
docker run --rm airbyte/source-ecforce:0.1.1 spec
docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-ecforce:0.1.1 check --config /secrets/config.json
```

### 4. 設定例

```json
{
  "domain": "myshop.ec-force.com",
  "api_token": "your-api-token-here",
  "company_name": "my-company",
  "start_date": "2023-01-01",
  "end_date": "2025-01-14",
  "include_notes": true,
  "gcs_bucket": "my-ecforce-cache",
  "gcs_service_account_key": "{\"type\": \"service_account\", ...}",
  "request_interval": 2
}
```

## 開発者向け情報

### ディレクトリ構成

```
source-ecforce/
├── source_ecforce/
│   ├── source.py       # メインのソースクラス
│   ├── spec.yaml       # コネクタの仕様定義
│   └── run.py          # エントリーポイント
├── unit_tests/         # ユニットテスト
├── metadata.yaml       # Airbyteメタデータ（ビルド設定含む）
└── pyproject.toml      # Python依存関係
```

### テストの実行

```bash
# ユニットテスト
poetry run pytest unit_tests/

# 特定のテストのみ実行
poetry run pytest unit_tests/test_streams.py -k "test_parse_response"
```

## トラブルシューティング

### よくある問題

1. **レート制限エラー（429）**
   - `request_interval`を増やして再試行
   - デフォルトは1秒ですが、5秒や10秒に増やすことを推奨

2. **GCS接続エラー**
   - サービスアカウントキーのJSON形式を確認
   - バケットへのアクセス権限を確認

3. **大量データの同期**
   - 月次スライスにより自動的に分割処理
   - メモリ不足の場合はワーカーのリソースを増やす

## ライセンス

MIT License

## サポート

- ecforce API ドキュメント: [ecforce開発者向けドキュメント](https://developers.ec-force.com/)
- Airbyte ドキュメント: [https://docs.airbyte.com/](https://docs.airbyte.com/)
- 問題報告: このリポジトリのIssuesへ