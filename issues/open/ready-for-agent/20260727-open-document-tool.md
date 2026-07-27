---
title: "open_document tool を追加する"
---

# open_document tool を追加する

## 背景

FreeCAD MCP には `create_document`（新規空ドキュメント）と `reload_document`（既に開いているドキュメントのディスク再読込）があるが、ディスク上の既存 `.FCStd` をパス指定で開く手段がない。addon 側では `reload_document` 内で `FreeCAD.openDocument(file_path)` を既に使っている。

## 目的

MCP tool `open_document` を追加し、絶対パスの既存 `.FCStd` を開け、そのドキュメントをアクティブにできるようにする。

## 利用者意図・成果物・成功条件・制約

- **意図:** 既存 FreeCAD ファイルを MCP から開けるようにする（`create` と `reload` のギャップを埋める）
- **成果物:** `open_document` MCP tool（RPC / client / operation / server 配線と README）
- **成功条件:** 絶対パスの `.FCStd` を開きアクティブ化できる。既開なら再オープンせず成功を返しアクティブ化する
- **制約:** `.FCStd` のみ、絶対パスのみ

## 範囲

### 対象

- `open_document` MCP tool の追加
- 既に同じファイルが開いている場合は再オープンせず既存ドキュメントを使い、成功を返す
- 開いた／再利用したドキュメントをアクティブにする
- 相対パス・非 `.FCStd`・存在しないパスはエラーを返す
- README Tools 一覧への追記

### 対象外

- STEP / IGES 等のインポート形式
- `reload_document` の置き換えや仕様変更
- 相対パス解決
- CONTEXT.md / ADR 新規作成（既存「document」語彙の延長で足りる）
- FreeCAD 統合の自動 E2E（リポジトリに FreeCAD 依存の test harness がない）

## 確定した判断

| 判断 | 採用 | 不採用と理由 |
| --- | --- | --- |
| 既開時 | 既存を使い成功＋アクティブ化 | エラー（使い勝手が悪い）／reload 相当（責務が `reload_document` と重複） |
| アクティブ化 | する（`FreeCAD.setActiveDocument`） | しない（`get_view` 等との流れが悪い） |
| 形式 | `.FCStd` のみ（拡張子は大小無視） | 任意形式（document 操作の境界が曖昧） |
| パス | 絶対パスのみ | 相対（MCP の cwd が不定） |
| 成功レスポンス形 | `{success, document_name}`（`create`/`reload` と同じ） | `already_open` フラグ追加（Interface を広げず、文言で区別可） |
| 既開判定 | 開いている各 `doc.FileName` と入力パスを `os.path.realpath` で比較 | ドキュメント名だけで判定（ファイル実体とずれる） |

## 変更する Module と Interface

`reload_document` と同じ縦スライスを踏襲する。

1. **Addon RPC**（`addon/FreeCADMCP/rpc_server/rpc_server.py`）
   - Interface: `open_document(file_path: str) -> dict`
   - 成功: `{"success": True, "document_name": <str>}`
   - 失敗: `{"success": False, "error": <str>}`
   - Implementation（GUI スレッド）:
     1. 入力検証（絶対パス / `.FCStd` / ファイル存在）
     2. 既開なら `setActiveDocument` してその名前を返す
     3. 未開なら `FreeCAD.openDocument(file_path)`（通常アクティブ化される）。必要なら明示的に `setActiveDocument`
     4. 開いたドキュメント名を返す
2. **MCP client**（`src/freecad_mcp/freecad_client.py`）: `open_document(file_path) -> dict`
3. **Operation**（`src/freecad_mcp/operations/core.py` + `__init__.py`）: `open_document_operation` — 成功／失敗を text response に整形
4. **MCP tool**（`src/freecad_mcp/server.py`）: `@mcp.tool() open_document(ctx, file_path: str)`
5. **README.md**: Tools 一覧に追記

### error modes

- 相対パス → error（ドキュメント状態は変更しない）
- 拡張子が `.FCStd` でない → error
- ファイルが存在しない → error
- `openDocument` 失敗 → error 文字列を返す
- 既開 → success（再オープンしない）

### 互換性・security・rollback

- 新規 tool のみ。既存 tool の Interface は変えない
- 任意パスのオープンは `execute_code` と同程度のローカル権限前提。絶対パス強制で誤相対解決を避ける
- 失敗時は新規ドキュメントを残さない（既開再利用時は閉じない）
- 問題があれば tool 追加分を revert すれば足りる

## Plan

1. Addon に `open_document` / `_open_document_gui` を追加する
2. client・operation・server を配線する
3. README を更新する
4. 受け入れ条件を静的読解と（可能な場合）手動 RPC 確認で検証する

## 検証

守る behavior: 「絶対パス `.FCStd` を開き／再利用し、アクティブな document として使える」

守る seam: Addon RPC `open_document`（検証・既開判定・open・activate の Locality）

| 受け入れ条件 | 手段 | 観察 |
| --- | --- | --- |
| 絶対パス `.FCStd` を開くと `list_documents` に現れアクティブ | 静的読解 + 手動（FreeCAD RPC 起動時） | RPC `open_document` → `list_documents`、ActiveDocument 名 |
| 既開時は再オープンせず成功＋アクティブ | 静的読解（既開枝が `openDocument` を呼ばない）+ 手動 | 2 回呼び出しで document 数が増えない |
| 相対／非 FCStd／不存在は error、状態を壊さない | 静的読解（検証が open より前）+ 手動 | error 戻り、`list_documents` 不変 |
| README に記載 | grep | `open_document` が Tools 節にある |

- 自動テスト: リポジトリに test suite / FreeCAD harness がないため新規 E2E は置かない
- CI 観測: なし（現状 CI に FreeCAD なし）。review 時の静的確認を主証拠とする
- fixture: 手動確認時のみ一時 `.FCStd` を用意（リポジトリへ commit しない）

## 受け入れ条件

- [ ] 絶対パスの既存 `.FCStd` を `open_document` で開くと、そのドキュメントが `list_documents` に現れ、アクティブになる
- [ ] 同じファイルが既に開いている場合、再オープンせず成功を返し、そのドキュメントがアクティブになる
- [ ] 相対パス、`.FCStd` 以外、存在しないパスではエラーを返し、ドキュメント状態を壊さない
- [ ] README の Tools 一覧に `open_document` が記載される
- [ ] RPC → client → operation → MCP tool の配線が `reload_document` と同型である（静的読解）

## Evidence

- `create_document` / `reload_document` / `list_documents` はあるが `open_document` はない（`src/freecad_mcp/server.py`）
- `FreeCAD.openDocument(file_path)` は `_reload_document_gui` で使用済み（`addon/FreeCADMCP/rpc_server/rpc_server.py`）
- 成功 dict 形は `{"success": True, "document_name": ...}` が既存パターン
- リポジトリに `test_*.py` / pytest 設定なし（`pyproject.toml`）

## 未決定事項

- なし（実装可能な状態）

## 完了記録

- 未完了
