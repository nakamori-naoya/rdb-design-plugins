# コマンドデータモデル — 図書館の貸出（業務制約の抜粋）

物理設計の検査の正例として、write-doc の command-data-model 型の見本から、テーブルの見出しと業務制約だけを抜き出したもの。

## テーブル定義

### `loans`（貸出）

#### 業務制約: 一冊の本の貸出中か延滞の貸出は一つ

`status`が`lent`か`overdue`の貸出は、同じ`book_number`について一つしか無い（BDD-003）。

#### 業務制約: 一人の貸出中と延滞の貸出は5冊まで

`status`が`lent`か`overdue`の貸出は、同じ`user_number`について5つを超えない（BDD-002）。

#### 業務制約: 現在の版は最後のイベントの版

`current_version`は、その貸出の`loan_base_events`の最大の`version`と等しい（BDD-005）。

### `loan_base_events`（貸出に起きたこと）

### `loan_lent_events`（本を借りた）

### `loan_returned_events`（本を返した）

### `loan_marked_overdue_events`（延滞にした）

### `overdue_notice_requested_events`（延滞の通知を頼んだ）

### `overdue_notice_claimed_events`（延滞の通知を引き受けた）

#### 業務制約: 同じ要求の同じ版の回収は一つ

`request_id`と`version`の組は一意である（BDD-009）。

### `overdue_notice_succeeded_events`（延滞の通知を送った）
