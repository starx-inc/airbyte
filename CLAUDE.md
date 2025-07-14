# Claude AI Assistant Guide for Airbyte

## Repository Overview
Airbyteは、API、データベース、ファイルからデータウェアハウス、データレイク、データレイクハウスへのELT/ELTデータパイプライン用の主要なデータ統合プラットフォームです。

## Key Areas for Review
- **Connector Development**: `airbyte-integrations/connectors/`内のソース・デスティネーションコネクタ
- **CDK Framework**: `airbyte-cdk/`内のコネクタ開発キット
- **Build System**: Gradleベースのビルド設定
- **Testing**: 統合テストとパフォーマンステスト

## Code Review Focus Points
1. **Connector Implementation**: manifest.yaml設定、Python CDK使用方法
2. **Data Pipeline**: ストリーム処理、増分同期、状態管理
3. **Performance**: 大量データ処理、メモリ使用量
4. **Error Handling**: 接続エラー、レート制限、リトライ機能
5. **Security**: 認証情報管理、データ暗号化

## Common Patterns
- Declarative connectors using manifest.yaml
- Python CDK for custom logic
- Bulk CDK for high-performance destinations
- Incremental sync with cursor fields

## Testing Guidelines
- Unit tests for connector logic
- Integration tests with real APIs
- Performance tests for large datasets

## Required Secrets Configuration
以下のシークレットをGitHubリポジトリ設定で追加する必要があります：
- `APP_ID`: GitHub App ID
- `APP_PRIVATE_KEY`: GitHub App秘密鍵
- `AWS_ROLE_TO_ASSUME`: Bedrock Claude利用用のAWS IAMロール

## Usage
- **自動PRレビュー**: PRを作成すると自動的にClaudeがレビューを実行
- **@claudeコメント**: Issue/PRコメントで`@claude`をメンションして質問や相談が可能
- **エラーハンドリング**: レビュー失敗時も継続実行される設定
- **タイムアウト**: 長時間実行の制御機能付き
