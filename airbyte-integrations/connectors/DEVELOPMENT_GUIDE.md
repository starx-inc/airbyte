# Airbyte Source Connector 開発ガイド - Source Test

このドキュメントでは、JSONPlaceholder APIからデータを取得するAirbyteソースコネクタ「Source Test」の開発手順を詳しく説明します。

## 目次

1. [概要](#概要)
2. [前提条件](#前提条件)
3. [プロジェクトのセットアップ](#プロジェクトのセットアップ)
4. [コネクタの実装](#コネクタの実装)
5. [テスト](#テスト)
6. [Dockerイメージのビルド](#dockerイメージのビルド)
7. [トラブルシューティング](#トラブルシューティング)
8. [参考資料](#参考資料)

## 概要

Source Testは、[JSONPlaceholder](https://jsonplaceholder.typicode.com/) APIのusersエンドポイントからユーザーデータを取得するシンプルなAirbyteソースコネクタです。

### 主な機能
- JSONPlaceholder APIからのユーザーデータ取得
- フルリフレッシュ同期モード対応
- スキーマ自動検出
- Dockerコンテナとしての実行

## 前提条件

### 必要なソフトウェア
- Python 3.10-3.12（3.13以降はairbyte-cdkが未対応）
- Poetry（Pythonパッケージ管理ツール）
- Docker（コンテナイメージのビルド用）
- Git

### 環境準備
```bash
# Poetryのインストール（未インストールの場合）
curl -sSL https://install.python-poetry.org | python3 -

# Pythonバージョンの確認
python3 --version  # 3.10-3.12であることを確認
```

## プロジェクトのセットアップ

### 1. ディレクトリ構造の作成

```bash
# Airbyteリポジトリのコネクタディレクトリに移動
cd airbyte-integrations/connectors/

# コネクタ用ディレクトリを作成
mkdir source-test
cd source-test
```

### 2. Poetry プロジェクトの初期化

```bash
# Poetry プロジェクトを初期化
poetry init
```

### 3. pyproject.toml の設定

```toml
[tool.poetry]
name = "source-test"
version = "0.1.0"
description = "Source implementation for Test."
authors = ["Airbyte <contact@airbyte.io>"]
license = "MIT"
readme = "README.md"
documentation = "https://docs.airbyte.com/integrations/sources/test"
homepage = "https://airbyte.com"
repository = "https://github.com/airbytehq/airbyte"
packages = [ {include = "source_test"}, {include = "main.py"} ]

[tool.poetry.dependencies]
python = "^3.10,<3.13"
airbyte-cdk = "^6.58.0"

[tool.poetry.scripts]
source-test = "source_test.run:run"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
pytest-mock = "^3.6.1"
requests-mock = "^1.9.3"

[build-system]
requires = ["poetry-core>=2.0.0,<3.0.0"]
build-backend = "poetry.core.masonry.api"
```

### 4. 依存関係のインストール

```bash
# Python 3.12環境を使用
poetry env use python3.12

# 依存関係をインストール
poetry install
```

## コネクタの実装

### 1. ディレクトリ構造

```
source-test/
├── source_test/
│   ├── __init__.py
│   ├── source.py
│   ├── run.py
│   └── spec.yaml
├── integration_tests/
│   └── configured_catalog.json
├── secrets/
│   └── config.json
├── main.py
├── metadata.yaml
├── pyproject.toml
├── poetry.lock
├── Dockerfile
└── README.md
```

### 2. metadata.yaml - コネクタメタデータ

```yaml
connectorType: source
definitionId: cbff570a-7049-4922-aa5e-c6cdf0288c05
name: Test
dockerRepository: airbyte/source-test
dockerImageTag: 0.1.0
metadataSpecVersion: "1.0"
connectorSubtype: api
documentationUrl: https://docs.airbyte.com/integrations/sources/test
supportLevel: community
license: MIT
tags:
  - language:python
  - keyword:api
  - keyword:users
  - keyword:jsonplaceholder
```

### 3. source_test/source.py - メインロジック

```python
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream


class UsersStream(HttpStream):
    url_base = "https://jsonplaceholder.typicode.com/"
    primary_key = "id"

    def path(self, **kwargs) -> str:
        return "users"

    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        return response.json()

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        # JSONPlaceholder APIはページネーションなし
        return None

    def get_json_schema(self) -> Mapping[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "username": {"type": "string"},
                "email": {"type": "string"},
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "suite": {"type": "string"},
                        "city": {"type": "string"},
                        "zipcode": {"type": "string"},
                        "geo": {
                            "type": "object",
                            "properties": {
                                "lat": {"type": "string"},
                                "lng": {"type": "string"}
                            }
                        }
                    }
                },
                "phone": {"type": "string"},
                "website": {"type": "string"},
                "company": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "catchPhrase": {"type": "string"},
                        "bs": {"type": "string"}
                    }
                }
            }
        }


class SourceTest(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        try:
            stream = UsersStream(authenticator=None)
            records = stream.read_records(sync_mode="full_refresh")
            next(records)
            return True, None
        except Exception as e:
            return False, f"Unable to connect to JSONPlaceholder API: {str(e)}"

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        return [UsersStream(authenticator=None)]
```

### 4. source_test/run.py - エントリーポイント

```python
#!/usr/bin/env python3

import sys

from airbyte_cdk.entrypoint import launch
from .source import SourceTest


def run():
    source = SourceTest()
    launch(source, sys.argv[1:])


if __name__ == "__main__":
    run()
```

### 5. source_test/spec.yaml - 接続仕様

```yaml
documentationUrl: https://docs.airbyte.com/integrations/sources/test
connectionSpecification:
  $schema: http://json-schema.org/draft-07/schema#
  title: Test Spec
  type: object
  additionalProperties: false
  properties: {}
```

### 6. main.py - Dockerエントリーポイント

```python
import sys

from source_test import run

if __name__ == "__main__":
    run.run()
```

### 7. secrets/config.json - 設定ファイル

```json
{}
```

### 8. integration_tests/configured_catalog.json - カタログ設定

```json
{
  "streams": [
    {
      "stream": {
        "name": "users_stream",
        "json_schema": {
          "$schema": "http://json-schema.org/draft-07/schema#",
          "type": "object",
          "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "username": {"type": "string"},
            "email": {"type": "string"},
            "address": {
              "type": "object",
              "properties": {
                "street": {"type": "string"},
                "suite": {"type": "string"},
                "city": {"type": "string"},
                "zipcode": {"type": "string"},
                "geo": {
                  "type": "object",
                  "properties": {
                    "lat": {"type": "string"},
                    "lng": {"type": "string"}
                  }
                }
              }
            },
            "phone": {"type": "string"},
            "website": {"type": "string"},
            "company": {
              "type": "object",
              "properties": {
                "name": {"type": "string"},
                "catchPhrase": {"type": "string"},
                "bs": {"type": "string"}
              }
            }
          }
        },
        "supported_sync_modes": ["full_refresh"],
        "source_defined_primary_key": [["id"]]
      },
      "sync_mode": "full_refresh",
      "destination_sync_mode": "overwrite"
    }
  ]
}
```

## テスト

### ローカルテスト（Poetry使用）

```bash
# 1. spec コマンド - 仕様の確認
poetry run source-test spec

# 2. check コマンド - 接続確認
poetry run source-test check --config secrets/config.json

# 3. discover コマンド - スキーマ探索
poetry run source-test discover --config secrets/config.json

# 4. read コマンド - データ読み取り
poetry run source-test read --config secrets/config.json --catalog integration_tests/configured_catalog.json
```

### 期待される出力

**spec コマンド:**
```json
{"type":"SPEC","spec":{"connectionSpecification":{...}}}
```

**check コマンド:**
```json
{"type":"LOG","log":{"level":"INFO","message":"Check succeeded"}}
{"type":"CONNECTION_STATUS","connectionStatus":{"status":"SUCCEEDED"}}
```

**discover コマンド:**
```json
{"type":"CATALOG","catalog":{"streams":[...]}}
```

**read コマンド:**
```json
{"type":"RECORD","record":{"stream":"users_stream","data":{...}}}
```

## Dockerイメージのビルド

### 1. Dockerfile の作成

```dockerfile
FROM python:3.12-slim

# Bash is installed for more convenient debugging.
RUN apt-get update && apt-get install -y bash && rm -rf /var/lib/apt/lists/*

WORKDIR /airbyte/integration_code
COPY source_test ./source_test
COPY main.py ./
COPY pyproject.toml ./
COPY poetry.lock ./
COPY README.md ./

# Install poetry
RUN pip install poetry

# Configure poetry to not use virtual environments
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --only main

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=0.1.0
LABEL io.airbyte.name=airbyte/source-test
```

### 2. Dockerイメージのビルド

```bash
docker build . -t airbyte/source-test:0.1.0
```

### 3. Dockerイメージのテスト

```bash
# spec コマンド
docker run --rm airbyte/source-test:0.1.0 spec

# check コマンド
docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-test:0.1.0 check --config /secrets/config.json

# discover コマンド
docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-test:0.1.0 discover --config /secrets/config.json

# read コマンド
docker run --rm -v $(pwd)/secrets:/secrets -v $(pwd)/integration_tests:/integration_tests airbyte/source-test:0.1.0 read --config /secrets/config.json --catalog /integration_tests/configured_catalog.json
```

## トラブルシューティング

### よくある問題と解決方法

#### 1. Python バージョンエラー
```
The current project's supported Python range (>=3.13) is not compatible
```
**解決方法:** `pyproject.toml`のPythonバージョンを`^3.10,<3.13`に設定し、`poetry env use python3.12`を実行

#### 2. spec.yaml が見つからない
```
FileNotFoundError: Unable to find spec.yaml or spec.json in the package
```
**解決方法:** `spec.yaml`を`source_test`ディレクトリ内に配置

#### 3. next_page_token メソッドの実装エラー
```
Can't instantiate abstract class UsersStream without an implementation for abstract method 'next_page_token'
```
**解決方法:** `UsersStream`クラスに`next_page_token`メソッドを実装

#### 4. スキーマファイルが見つからない
```
No such file or directory: 'schemas/users_stream.json'
```
**解決方法:** `get_json_schema`メソッドを実装してスキーマを直接返す

## ベストプラクティス

### 1. エラーハンドリング
- API接続エラーは適切にキャッチし、わかりやすいエラーメッセージを返す
- `check_connection`メソッドで詳細なエラー情報を提供

### 2. スキーマ定義
- APIレスポンスに基づいて正確なスキーマを定義
- ネストされたオブジェクトも適切に型定義

### 3. ページネーション
- APIがページネーションをサポートする場合は`next_page_token`メソッドを実装
- 今回のJSONPlaceholder APIはページネーションなしのため`None`を返す

### 4. 認証
- 認証が必要なAPIの場合は適切な`Authenticator`クラスを実装
- 今回は認証不要のため`authenticator=None`

## 次のステップ

### 機能拡張の例
1. **増分同期の実装**: `stream_slices`メソッドを実装して増分同期をサポート
2. **他のエンドポイントの追加**: posts、comments、todosなどのストリームを追加
3. **レート制限の実装**: `request_rate_limiter`メソッドでAPI制限に対応
4. **エラーリトライの実装**: `should_retry`メソッドでリトライロジックを追加

### プロダクション対応
1. **ユニットテストの追加**: `unit_tests/`ディレクトリにテストを実装
2. **CI/CDパイプライン**: GitHub Actionsでテストとビルドを自動化
3. **ログの改善**: より詳細なログメッセージを追加
4. **ドキュメント**: ユーザー向けドキュメントを充実させる

## 参考資料

- [Airbyte公式ドキュメント](https://docs.airbyte.com/)
- [カスタムPythonコネクタチュートリアル](https://docs.airbyte.com/platform/connector-development/tutorials/custom-python-connector/environment-setup)
- [コネクタメタデータファイル仕様](https://docs.airbyte.com/platform/connector-development/connector-metadata-file)
- [カスタムコネクタの使用方法](https://docs.airbyte.com/platform/operator-guides/using-custom-connectors)
- [JSONPlaceholder API](https://jsonplaceholder.typicode.com/)

## まとめ

このガイドでは、シンプルなAirbyteソースコネクタの開発手順を説明しました。基本的な実装から始めて、必要に応じて機能を追加していくことで、より複雑なAPIにも対応できるコネクタを開発できます。