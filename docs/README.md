# Design Docs

`docs/` は `zmk-usb-bridge-gui` の設計文書置き場です。
まずは `PoC の前提整理` を優先し、詳細設計は必要になった段階で段階的に分割します。

## 構成

### `foundation/`

プロジェクト全体で共有する前提、目標、PoC の境界、実装方針を置く。

- `foundation/project-concept.md`: 別 project 化の理由、PoC 前提、初期アーキテクチャ、難易度見立て
- `foundation/protocol-v1.md`: GUI と receiver の `CDC ACM protocol v1` 正本
- `foundation/candidate-listing-policy.md`: 候補一覧へ載せる条件、上限、並び順、GUI 公開モデル
- `foundation/desktop-app-foundation.md`: desktop app 技術スタック、COM port 自動検出、Windows 配布方針
- `foundation/phase2-and-beyond-implementation-plan.md`: `Phase 2` 以降の残タスク、実装順、completion までの計画
- `foundation/testing-policy.md`: PoC フェーズにおけるテストの優先順位、追加基準、後回しにする範囲
- `foundation/poc-evaluation.md`: PoC の pass / hold / fail 条件

### `validation/`

PoC の手動確認結果、未確認項目、review 用 evidence を置く。

- `validation/phase1-validation-log.md`: `DesktopApp Phase 1` の確認結果と未解決事項の記録

## 読み方と記述ルール

- 初めて読む場合は `foundation/project-concept.md` を入口にし、必要な詳細は各正本 document を参照する
- 典型的な読み順は `foundation/project-concept.md` -> `foundation/protocol-v1.md` -> `foundation/candidate-listing-policy.md` -> `foundation/desktop-app-foundation.md` -> `foundation/phase2-and-beyond-implementation-plan.md` -> `foundation/testing-policy.md` -> `foundation/poc-evaluation.md` -> `validation/phase1-validation-log.md` とする
- まず全体前提を `foundation/` にまとめる
- 既存 `zmk-usb-bridge` の設計との差分は、前提と理由が分かる形で明示する
- 実装前に決め切れない点は `Open Questions` と `Validation Needed` に残す
- PoC で確かめる事項と、MVP 以降で持ち越す事項を分けて書く
