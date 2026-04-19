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
- `foundation/debug-log-foundation.md`: 実機デバッグ用の統合 log 収集方針、record 形式、保存方針
- `foundation/testing-policy.md`: PoC フェーズにおけるテストの優先順位、追加基準、後回しにする範囲
- `foundation/poc-evaluation.md`: PoC の pass / hold / fail 条件

### `plans/`

実装中の変更単位ごとに作る、一時的な implementation plan を置く。

- `plans/phase2-and-beyond-implementation-plan.md`: `Phase 2` 以降の残タスク、実装順、completion までの計画
- plan は実装が終わったら使い捨てを前提とし、確定した静的仕様だけを `foundation/` や `validation/` へ分配する
- plan 内では `Open Questions`、実装順、作業の分解、carry-over 項目を扱ってよい
- plan を正本にしない。後から継続参照したい内容は、対応する正本 document へ移してから plan を閉じる

### `validation/`

PoC の手動確認結果、未確認項目、review 用 evidence を置く。

- `validation/phase1-validation-log.md`: `DesktopApp Phase 1` の確認結果と未解決事項の記録

## 読み方と記述ルール

- 初めて読む場合は `foundation/project-concept.md` を入口にし、必要な詳細は各正本 document を参照する
- 典型的な読み順は `foundation/project-concept.md` -> `foundation/protocol-v1.md` -> `foundation/candidate-listing-policy.md` -> `foundation/desktop-app-foundation.md` -> `foundation/debug-log-foundation.md` -> `foundation/testing-policy.md` -> `foundation/poc-evaluation.md` -> `plans/phase2-and-beyond-implementation-plan.md` -> `validation/phase1-validation-log.md` とする
- まず全体前提を `foundation/` にまとめる
- 実装途中の論点整理や作業順は `plans/` に置き、完了後は残さない前提で扱う
- 既存 `zmk-usb-bridge` の設計との差分は、前提と理由が分かる形で明示する
- 実装前に決め切れない点は `Open Questions` と `Validation Needed` に残す
- PoC で確かめる事項と、MVP 以降で持ち越す事項を分けて書く
