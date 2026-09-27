# RDB物理設計 — 図書館の貸出（物理制約の抜粋）

物理設計の検査の正例として、write-doc の rdb-physical-design 型の見本から、物理制約の節だけを抜き出したもの。

## 業務制約は一意制約、条件付きの更新、SERIALIZABLE で守る

| 制約名 | 対象 | 実現方法 | 適用時点 | 違反時の扱い |
|---|---|---|---|---|
| 一冊の本の貸出中か延滞の貸出は一つ | `loans` | `book_number`の部分一意index（`status IN ('lent', 'overdue')`） | 行の書込み時 | SQLSTATE `23505`を「貸出中の本を借りる」へ変換する。やり直さない |
| 一人の貸出中と延滞の貸出は5冊まで | `loans` | `SERIALIZABLE`のトランザクションで件数を読んでから書く | コミット時 | SQLSTATE `40001`ならトランザクションの中で最大3回やり直す |
| 現在の版は最後のイベントの版 | `loans`、`loan_base_events` | `loans`の`current_version`を読んだ版で条件付きに更新し、`loan_base_events`の`loan_id, version`の一意制約と同じトランザクションで組み合わせる | 状態変更時 | 更新件数0か`23505`なら競合として返す。やり直さない |
| 同じ要求の同じ版の回収は一つ | `overdue_notice_claimed_events` | `request_id, version`の一意制約 | 行の書込み時 | SQLSTATE `23505`なら、その回収を積まず、送り手はその要求を送らない。やり直さない |

値の範囲のCHECKは、ドメインモデルだけが書く業務の表（`loans`、基底イベント、詳細イベント）には置かない。値が正しいかを決めるのはドメインモデルで、決める場所を二つにしないためである。一方、技術処理の表はドメインモデルの外にある送り手が書く。そこで、`overdue_notice_claimed_events.version`が1以上であることと、`overdue_notice_claimed_events.worker_id`が空でないことは、CHECKで拒む。
