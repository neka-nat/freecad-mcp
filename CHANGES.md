# Changes

## [Unreleased]

### Added

#### 2026-07-27 11:40:10 open_document tool を追加

- 変更: 絶対パスの既存 `.FCStd` を開く MCP tool `open_document` を追加した。同じファイルが既に開いていれば再オープンせずアクティブ化する。
- Why: `create_document`（新規）と `reload_document`（既開の再読込）の間に、ディスク上の既存ドキュメントを開く手段がなかったため。
- Why not: 相対パス解決や STEP 等のインポート形式対応は、cwd 不定と document 操作の境界曖昧化を避けるため対象外とした。既開時の閉じ直しは `reload_document` の責務と重複するため採用しなかった。
