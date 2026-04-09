# Implementation Start Checklist

## Purpose

- `zmk-usb-bridge-gui` を実装開始できる状態まで持っていくためのチェックリスト
- `実装前に固定すべきこと` と `PoC で検証しながら決めてよいこと` を分ける
- 今後の議論を `順番に 1 項目ずつ詰める` ための土台にする
- 実装の全体像と PoC の進め方は [`project-concept.md`](project-concept.md) を参照する

## How To Use

- 上から順に詰める
- 各項目は、`決定` か `PoC で検証して判断` のどちらかに落とす
- `完了条件` を満たしたらチェックを入れる
- 新しい論点が出ても、まずは既存項目のどこに属するかを確認してから追加する

## Blocking Before Implementation

### 0. Project boundary を明文化する

- [x] この project のスコープを誤読されない形で固定する

決めること:
- `zmk-usb-bridge-gui` が `ZMK keyboard firmware project` ではなく `receiver firmware + desktop app` を扱う独立 Zephyr project であること
- `既存 ZMK キーボード無改造` と `receiver 側 endpoint 追加` が両立する理由
- `build / flash / deliverable` の単位をどこで分けるか

なぜ必要か:
- reviewer が `keyboard 側も変更前提の project` と誤読すると、設計全体が矛盾して見えるため
- `CDC ACM 2 endpoint` の話がどのデバイスの仕様かを最初に固定する必要があるため

完了条件:
- `project-concept.md` 冒頭で誤読しにくい形で前提が説明されている
- `receiver 側仕様` と `keyboard 側無改造` の関係が 1 箇所で読める
- 今後の設計文書でもこの前提を使い回せる

現在の正本:
- [`project-concept.md`](project-concept.md) の `Project Boundary`

### 1. PoC の完了ラインを固定する

- [x] `PoC の第一段階` をどこまでにするか決める

決めること:
- 最初の到達点を `状態表示まで`、`候補一覧まで`、`手動 pairing まで` のどこに置くか
- `PoC 完了` と見なす最小機能セットを何にするか
- 初期 bring-up の `参照 board / target environment` をどこまで固定するか

なぜ必要か:
- firmware と desktop app の責務分割がここで決まる
- スコープが曖昧だと protocol と candidate cache の設計がぶれやすい

完了条件:
- 第一段階のゴールが 1 文で言える
- `PoC 完了条件` と `PoC 以降に回すこと` が分かれている
- bring-up の参照 board が `前提` なのか `正式固定` なのか区別できる

関連文書:
- [`project-concept.md`](project-concept.md) の `Initial PoC Scope` と `Recommended PoC Sequence`

現在の正本:
- [`project-concept.md`](project-concept.md) の `Phase 1 Completion Line`

### 2. GUI と receiver の protocol v1 を定義する

- [x] `CDC ACM protocol v1` の最小仕様を決める

決めること:
- message format を `line-delimited JSON` で固定するか
- `hello`、`status snapshot`、`command`、`ack`、`error`、`event` の最小セット
- candidate 一覧の出し方を `逐次 event` にするか、`snapshot + 差分` にするか
- 接続失敗や scan 完了をどう返すか
- `PoC 必須操作` を満たす最小 command / event の網羅範囲

なぜ必要か:
- GUI 実装と firmware 実装を並行に進められるようにするため
- COM port 自動検出や初期同期の仕様にも直結するため

完了条件:
- `受信 message 一覧` と `送信 command 一覧` が書けている
- 各 message に必須 field が定義されている
- 初回接続時のシーケンスが文章か図で説明できる
- `scan` と `bond erase` を含む PoC 必須操作の扱いが定義されている

関連文書:
- [`project-concept.md`](project-concept.md) の `Communication Model`

現在の正本:
- [`protocol-v1.md`](protocol-v1.md)

### 3. Candidate listing policy を固定する

- [x] 候補一覧の載せ方を決める

決めること:
- 一覧の上限件数
- `HID service`、`keyboard appearance`、`local name` をどう評価するか
- `keyboard appearance` が無い候補を非表示にするか、警告付き表示にするか
- candidate の寿命、更新、重複除去、並び順
- candidate cache を GUI にどう見せるか、その最小 field をどう置くか

なぜ必要か:
- GUI 上の一覧 UX と firmware の candidate cache モデルがここで決まる
- 誤候補が多いと PoC の価値そのものが下がる

完了条件:
- `表示対象` と `表示しない対象` のルールが書けている
- 一覧上限とソート方針が決まっている
- 接続後 validation で弾く条件が明記されている
- candidate cache の公開モデルが GUI 側の前提と矛盾しない

関連文書:
- [`project-concept.md`](project-concept.md) の `Candidate Listing Policy`

現在の正本:
- [`candidate-listing-policy.md`](candidate-listing-policy.md)

### 4. COM port 自動検出方式を決める

- [x] desktop app が receiver を見つける方法を固定する

決めること:
- `VID/PID 主体`、`hello 応答主体`、または併用のどれにするか
- GUI 用 CDC と log 用 CDC が複数見えたときの識別方法
- receiver 未接続時、複数接続時、再接続時の扱い
- GUI/log 用 CDC instance の前提を `仮置き` のままにするか、ここで正式化するか

なぜ必要か:
- desktop app の起動シーケンスと接続安定性に直結する
- Windows 優先 PoC の使い勝手を大きく左右する

完了条件:
- 自動検出フローが 1 つに決まっている
- GUI 用 endpoint と log 用 endpoint の見分け方が定義されている
- 失敗時の fallback 動作が決まっている
- USB 構成の仮定が COM port 検出仕様と矛盾しない

関連文書:
- [`project-concept.md`](project-concept.md) の `Current Assumptions` と `Communication Model`

現在の正本:
- [`desktop-app-foundation.md`](desktop-app-foundation.md) の `COM Port Detection Policy`

### 5. Desktop app 技術スタックを固定する

- [x] GUI 実装方式と配布方式を決める

決めること:
- 実装言語
- GUI toolkit
- serial 通信ライブラリ
- Windows 向け `EXE` 化手順

なぜ必要か:
- ディレクトリ構成、ビルド手順、CI、依存管理が全部ここに依存する
- PoC の速度と将来の配布性の両方に影響する

完了条件:
- `language + toolkit + package manager + bundler` が 1 セットに決まっている
- ローカル実行手順と Windows 配布手順が 1 つずつ書けている

関連文書:
- [`project-concept.md`](project-concept.md) の `Desktop App Direction`

現在の正本:
- [`desktop-app-foundation.md`](desktop-app-foundation.md) の `Technology Stack`

### 6. PoC の pass / fail 条件を決める

- [x] PoC の評価基準を固定する

決めること:
- `LaLapadGen2` が無改造で候補一覧に出ることを pass 条件に含めるか
- 手動 pairing 成立、再接続安定性、誤候補率の許容値
- `CDC ACM` 追加による回帰をどう判定するか

なぜ必要か:
- 実装後に `成立したかどうか` を判断できるようにするため
- Kill Criteria を実測ベースで判定できるようにするため

完了条件:
- `pass criteria` と `fail / hold criteria` が分かれている
- 計測方法または確認方法が項目ごとに書かれている

関連文書:
- [`project-concept.md`](project-concept.md) の `Validation Needed` は論点一覧として使う
- 正式な `pass / fail` 条件はこの item で固定し、後に `docs/validation/` へ移す

現在の正本:
- [`poc-evaluation.md`](poc-evaluation.md)

## Can Be Decided During PoC

### 7. Battery 表示の詳細

- [ ] battery 未取得時と取得失敗時の UI を詰める

現時点の扱い:
- 実装 blocker ではない
- 値取得後のみ表示、または `unknown` 表示のどちらが自然かを PoC で見る

### 8. macOS / Linux の扱い

- [ ] Windows PoC 後に基本利用阻害がないか確認する

現時点の扱い:
- 初期実装 blocker ではない
- ただし protocol や app 構成で将来対応を過度に難しくしない

### 9. UI の情報密度と見た目

- [ ] 詳細レイアウトと視認性を詰める

現時点の扱い:
- 最初は `状態表示 + 候補一覧 + 操作ボタン` の最小構成でよい
- 見た目の磨き込みは実装 blocker ではない

## Recommended Order

- `project-concept.md` の `Recommended PoC Sequence` と対応して読む
- `project-concept.md` が `実装の進め方`、この節が `実装前の意思決定順` を表す

1. `PoC の完了ライン`
2. `protocol v1`
3. `candidate listing policy`
4. `COM port 自動検出方式`
5. `desktop app 技術スタック`
6. `PoC の pass / fail 条件`

## Next Discussion Target

- blocking item `1` から `6` までは完了
- 次の着手候補は `desktop app skeleton` と `receiver 側 protocol stub` の実装開始
- `Can Be Decided During PoC` の項目は、Phase 1 実装が立ち上がってから順次詰める
