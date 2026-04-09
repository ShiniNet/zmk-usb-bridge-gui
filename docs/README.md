# Design Docs

`docs/` は `zmk-usb-bridge-gui` の設計文書置き場です。
まずは `PoC の前提整理` を優先し、詳細設計は必要になった段階で段階的に分割します。

## 構成

### `foundation/`

プロジェクト全体で共有する前提、目標、PoC の境界、実装方針を置く。

- `foundation/project-concept.md`: 別 project 化の理由、PoC 前提、初期アーキテクチャ、難易度見立て

## 運用ルール

- まず全体前提を `foundation/` にまとめる
- 既存 `zmk-usb-bridge` の設計との差分は、前提と理由が分かる形で明示する
- 実装前に決め切れない点は `Open Questions` と `Validation Needed` に残す
- PoC で確かめる事項と、MVP 以降で持ち越す事項を分けて書く

