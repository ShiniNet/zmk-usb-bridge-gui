# Testing Policy

## Purpose

- `zmk-usb-bridge-gui` におけるテストの役割と優先順位を明文化する
- `PoC 実装速度` と `デグレ検知` のバランスを、現在フェーズに合わせて固定する
- `どの層は今テストするか` と `どの層は後回しでよいか` を判断できるようにする

## Current Policy Summary

- 現フェーズでは `少数の高価値テストだけ維持し、広げすぎない` を基本方針とする
- 目的は `全面的な安心感` ではなく、`壊れると追跡コストが高い stable contract の保護` に置く
- `UI の細部` や `頻繁に変わる実装詳細` は、PoC 進行を阻害しないため原則として後回しにする
- 新機能ごとに機械的に test を増やすのではなく、追加基準は `Rules For Adding New Tests` に沿って絞る

## Why This Policy Fits This Project

- 本 project は `PoC` 段階であり、画面構成や操作導線は今後も変わりやすい
- 一方で `protocol v1`、`COM port attach rule`、`receiver state transition` のような境界条件は、後から壊れると手動確認が重い
- desktop app 側は `protocol`、`controller`、`runtime`、`session` に責務分離されており、境界の test を少数維持しやすい
- `AI による実装中心` であっても、非同期処理や状態遷移の regressions は起こりうるため、最小限の contract test は残す価値が高い

## Test Investment Rule By Layer

### いま維持する層

- `protocol parse / serialize`
- `candidate sorting` と `public candidate policy`
- `controller` の主要 state transition
- `runtime` の attach / detach / retry / reconnect 判断
- `session` の切断検知や例外時の最低限の recovery

### いま広げすぎない層

- `PySide6 widget` の細かな見た目や文言
- UI layout や表示順のような、PoC 中に変わりやすい表現
- 実機依存が強い end-to-end の全面自動化
- firmware 本実装の揺れに強く依存する test

### Phase 1 完了後に拡張を検討する層

- UI interaction test
- stub 依存を減らした integration test
- packaging / launch 動線の validation
- firmware と app をまたぐ end-to-end regression test

## Minimum Test Set During Active PoC Development

以下は `いま維持する層` に対応する、具体的な test case の代表例を示す。

- `hello`、`status_snapshot`、`candidate_snapshot`、`ack / error / event` の基本的な parse / roundtrip
- `scan_start -> scan_started -> candidate_upsert -> scan_complete` の代表的 sequence
- `scan_complete(result=stopped)` や `connection_state` など、状態遷移を誤ると UI が固着しやすい箇所
- `multiple receivers detected`、`hello.channel != gui`、`protocol_version` 不一致など、誤接続防止に関わる判定
- `disconnect -> rediscovery`、`scan watchdog timeout` など、再探索と復帰の基本動線

## Rules For Adding New Tests

- 新しい test は、次のどちらかに当てはまる場合だけ追加を推奨する
  - `外部契約を増やした`
  - `一度壊れた不具合を再発防止したい`

- 追加する test は、なるべく `1 つの contract` か `1 つの bug pattern` に閉じる
- 実装内部の細かな手順まで固定しすぎず、利用者影響のある振る舞いだけを固定する
- 仕様がまだ定まっていない層では、test を先に厚くするより document を先に固める

## Rules For Updating Existing Tests

- 実装修正のたびに既存 test を全面追従させるのではなく、`まだ守りたい contract か` を先に確認する
- 変更で不要になった test は、無理に延命せず削除してよい
- `PoC 中の表現変更` に弱い test は、より下位の stable な層へ寄せ替えることを優先する

## Local Execution

- desktop app の Python test は `unittest` を標準入口とする
- 実行コマンドは `uv run python -m unittest discover -s tests -v`
- 開発中は `全面実行を毎回必須` ではなく、変更影響の大きい test を優先して回してよい

## CI Policy

- `PoC Phase 1` の間は、CI による常時 test 実行を必須前提にはしない
- CI でどの test を常時回すかの固定は、`Phase 1` 完了後に test 範囲と実行コストが落ち着いた段階で検討する

## Mock / Stub Strategy

- 非同期 I/O や serial port 依存の test では、実ポートや実機への依存を避け、`stub`、`fake session`、`fake port` を優先して isolate する
- `runtime` や `session` の test は、port 列挙、clock、session factory、受信 event を差し替え可能な形で保ち、実機依存の確認は別の validation に分離する

## Review Checklist

- 今回の変更で `stable contract` を増やしているか
- その contract は手動確認より自動 test の方が安いか
- 追加する test は `PoC の変更速度` を不必要に落とさないか
- 既存 test は、現在も守るべき振る舞いを見ているか

## Relationship To Other Documents

- `protocol` の正本は [`protocol-v1.md`](protocol-v1.md)
- candidate 公開条件の正本は [`candidate-listing-policy.md`](candidate-listing-policy.md)
- desktop app の attach / discovery 前提は [`desktop-app-foundation.md`](desktop-app-foundation.md)
- 実装タスクの一覧は [`implementation-start-checklist.md`](implementation-start-checklist.md)
- ただし test の投資判断と優先順位の正本は **この document** とする
