# PoC Evaluation

## Purpose

- `PoC が成立したか` を実装後に判定できるようにする
- `pass` と `hold / fail` を分け、測り方も合わせて固定する

## Pass Criteria

### 1. Candidate Discovery

- `LaLapadGen2` が無改造のまま候補一覧に出る
- 確認方法: `bond erase` 済み状態から `scan_start` を実行し、`10 秒以内` に GUI 一覧へ対象が現れることを目視確認する

### 2. Manual Pairing / Connect

- GUI で選んだ `LaLapadGen2` に対して `pairing / connect` を開始でき、`connected` 状態へ到達する
- 確認方法: `connect_candidate` 実行後、`connection_state(connecting -> connected)` が観測され、接続先名が GUI に表示されることを確認する

### 3. Reconnect Stability

- 初回 pairing 成功後、keyboard 側電源の off/on もしくは一時切断から `15 秒以内` に bonded reconnect へ戻れる
- 確認方法: `PoC Phase 1` の pass 判定では、少なくとも `1 回` の切断復帰試験で GUI が `connected` に戻ることを確認する
- 補足: 成功率の安定性評価は `Hold Criteria` 側の `3 回試して 1 回以上失敗する` を基準に切り分ける

### 4. Bond Erase Recovery

- GUI から `bond_erase` を実行すると、receiver が初期状態へ戻り、再度 scan と pairing に進める
- 確認方法: `bond_erase` 後に `status_snapshot(receiver_state=idle)` 相当へ戻り、その後の `scan_start` で再び候補一覧を取得できることを確認する

### 5. USB Regression Safety

- `CDC ACM` 追加後も、接続成立時の HID bridge 動作が破綻しない
- 確認方法: `connected` 到達後に `key input`、`consumer control`、`mouse event` をそれぞれ実入力で確認し、入力欠落や明確なフリーズが出ないことを確認する

### 6. COM Port Detection Stability

- app 起動時と receiver 再接続時に、GUI 用 `COM port` を誤接続せず見つけられる
- 確認方法: 同一 Windows 環境で `app 起動時` と `receiver 抜き差し後` の両方で `hello.channel=gui` port へ再接続できることを確認する

## Hold Criteria

### 1. Candidate Noise Too High

- 一覧には出るが、誤候補が多すぎて target を見失いやすい
- 目安: `12 件上限` に達し続ける、または target が上位 `5 件` に安定して入らない
- 扱い: 即失敗ではなく、candidate policy 調整のため `hold` にする

### 2. Reconnect Is Intermittent

- bonded reconnect は通るが、観測ごとに成功率が大きくぶれる
- 目安: 3 回試して 1 回以上失敗する
- 扱い: `protocol` や `GUI` の価値判定は保留し、firmware 側安定化を優先する

### 3. GUI Detection Needs Manual Rescue

- 自動検出が不安定で、ときどき手動再試行が必要になる
- 目安: 単一 receiver 構成でも再列挙後に再接続できないケースがある
- 扱い: `COM port` 検出方式の再調整対象として `hold` にする

## Fail Criteria

### 1. Keyboard Modification Required

- `LaLapadGen2` を無改造では候補一覧へ出せない、または pairing 成立に keyboard 側変更が必要になる

### 2. Manual Pairing Never Reaches Connected

- `connect_candidate` を 3 回以上試しても `connected` に到達しない

### 3. CDC ACM Causes Core Regression

- `CDC ACM` 追加により HID bridge 入力や再接続が明確に悪化する
- 例: 接続はできても `key input`、`consumer control`、`mouse event` のいずれかが安定しない、抜き差しのたびに接続不能になる

### 4. Candidate Listing Loses Product Value

- 候補一覧が広すぎて、手動選択 UX の価値より誤操作リスクが上回る
- 目安: Tier A/Tier B の整理を入れても target を日常的に見分けられない

## Notes

- `pass` は `PoC の成立`
- `hold` は `成立可能性はあるが、追加検証が必要`
- `fail` は `この方向の価値仮説が崩れる`
