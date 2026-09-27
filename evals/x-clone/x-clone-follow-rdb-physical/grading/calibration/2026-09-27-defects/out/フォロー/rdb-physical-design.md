# RDB物理設計 — フォロー

フォローのコマンドデータモデルの7テーブルと7つの業務制約を、業務の意味を変えずに PostgreSQL 17.6 へ写す。この資料で決めるのは、制約、index、操作ごとの分離レベルと再試行、反映の要求を探すための派生の表の四つである。読み手は、フォローとフォローを外す操作、反映の担い手を実装するバックエンドのエンジニアで、この資料どおりに DDL とトランザクションの指定を書けるかを判断する。

- 二重のフォローは、フォロワーと相手の組の一意制約で拒む。
- フォロー中の上限5,000人は、SERIALIZABLE でフォロー中の行を数え、トランザクションの中で再試行して守る。
- 反映の要求は削除せず累積するので、反映待ちの要求だけを部分 index で探せるよう、要求ごとの予定の派生の表を置く。

実機で確かめた判断はまだ無く、すべて planned である。

## 対象と入力

- 対象DBMS: PostgreSQL
- 対象バージョン: 17.6
- コマンドデータモデル: `/private/tmp/e-RTX9Dp/home/cwd/data-model/フォロー/command-data-model.md`（版: SHA-256 の先頭 `b23c66870394`。リポジトリにコミットが無いので内容のハッシュで版を指す）
- クエリデータモデル: `/private/tmp/e-RTX9Dp/home/cwd/data-model/フォロー/query-data-model.md`（版: SHA-256 の先頭 `2a8cb8d049d5`）
- 要求資料: `/private/tmp/e-RTX9Dp/home/cwd/input/バックエンド要件.md`（版: SHA-256 の先頭 `b31ead0e51cb`）。要求発見の資料の形ではない要件の文書である
- 利用・負荷モデル: `/private/tmp/e-RTX9Dp/home/cwd/input/利用規模と負荷モデル.md`（2026年9月16日更新、SHA-256 の先頭 `b44d6a678ebb`）。値はどれも実測ではなく、設計のための仮定である
- 品質要求資料: `/private/tmp/e-RTX9Dp/home/cwd/input/非機能要件.md`（版: SHA-256 の先頭 `5b5d72ed73c6`）。応答時間と可用性の目標値は未定である
- 基盤構成資料: 未決。資料が無い。要件は一次データを単一の AlloyDB に置き、読み取りプールを持つと書くが、互換の版、複製の遅れ、バックアップの RPO と RTO は分からない
- 検証証拠: 未実施。実行計画、負荷試験、競合試験、復旧試験、運用観測の結果は無い
- 確認環境: 実機での確認は無い。作業環境からは PostgreSQL の公式資料へ接続できなかった。手元の PostgreSQL は 16 で、対象の版ではない。機能の根拠には PostgreSQL 17 の公式資料の URL を挙げたが、この実行では本文を開いて確かめていない（2026年9月27日）
- 想定規模: 論理量は、利用規模と負荷モデルの「累積データ量」による。フォロー変更は15万件/日で、算定期間3年の累計は1億6,425万件になる。増加率は0%と仮定されている。業務イベントと Outbox の記録は削除しない

二つのデータモデルが持つ ER図と BDD は、この資料には写さない。ほかの業務が持つ `users` はアカウントのコマンドデータモデルが持ち主で、この資料では外部キーの参照先と、読み取りに使う主キーとしてだけ扱う。

## 業務制約は、一意制約、版の条件付き更新、SERIALIZABLE で守る

物理制約は、コマンドデータモデルの業務制約と一対一に置いた。表の「違反時の扱い」で、どの SQLSTATE を業務知識のどの拒否に変換するかを確かめられる。

| 制約名 | 対象 | 実現方法 | 適用時点 | 違反時の扱い |
|---|---|---|---|---|
| 同じフォロワーと相手のフォローは一つ | `follows (follower_user_id, followee_user_id)` | 一意制約 `follows_follower_followee_key`（`status` を INCLUDE） | 行の書込み時（即時） | SQLSTATE `23505` は「フォロー中の相手をフォローする」に変換し、やり直さない。SERIALIZABLE では同じ衝突が `40001` として届くことがあり、そのときはトランザクションごとやり直して、読み直した状態で判定する |
| 自分へのフォローは無い | `follows (follower_user_id, followee_user_id)` | DB の制約は置かない。フォローする操作のドメインモデルが、行を読む前に拒む | トランザクションを始める前 | 「自分をフォローする」を返す。トランザクションに入らない |
| 一人のフォロー中は5,000まで | `follows` のうち、同じ `follower_user_id` で `status = 'following'` の行の集まり | フォローする操作を SERIALIZABLE で実行し、フォロー中の行を数えてから書く | コミット時 | 5,000人以上と数えたら「フォロー上限に達している利用者がフォローする」を返す。SQLSTATE `40001` と `40P01` のときは、トランザクションの中で最大3回やり直す |
| 現在の版は最後のイベントの版 | `follows (current_version, status)` と `follow_base_events (follow_id, version)` | 読んだ `current_version` を条件にした `follows` の更新と、`follow_base_events` への追加を、同じトランザクションで確定する | 状態変更時（即時） | 更新が0件なら、トランザクションを取り消して拒否を返す（フォローを外すなら「フォローしていない相手のフォローを外す」）。やり直さない。SERIALIZABLE の操作で `40001` になったときは、上の再試行に含める |
| 同じフォローの同じ版の出来事は一つ | `follow_base_events (follow_id, version)` | 一意制約 `follow_base_events_follow_version_key` | 行の書込み時（即時） | SQLSTATE `23505` は、版の条件付き更新と同じ競合として扱う |
| 業務イベント一件に要求は一つ | `follow_change_reflection_requested_events (source_event_id)` | 一意制約 `follow_change_reflection_requested_events_source_event_key` | 行の書込み時（即時） | SQLSTATE `23505` は実装の誤りとして扱い、トランザクションを取り消す。業務の拒否には変換しない |
| 同じ要求の同じ版の回収は一つ | `follow_change_reflection_claimed_events (request_id, version)` | 一意制約 `follow_change_reflection_claimed_events_request_version_key` | 行の書込み時（即時） | SQLSTATE `23505` なら、その回収を積まない。担い手はその要求を反映せず、次の要求へ進む。やり直さない |

「自分へのフォローは無い」を CHECK にしないのは、`follows` がドメインモデルだけが書く業務の表だからである。二つの列の値の正しさを、ドメインモデルと DB の二か所で判定させない。この制約は、ドメインモデルの外から書き込む経路を作らないことで守る。業務の表（`follows`、基底イベント、詳細イベント）の `status` と `event_type` には、値の範囲を守るため `CHECK (status IN ('following', 'not_following'))` のような CHECK を置く。

技術処理の表は反映の担い手が書き、値を確かめるドメインモデルが無い。そこで、次の三つを CHECK で拒む。

- `follow_change_reflection_claimed_events.version` が1以上であること
- `follow_change_reflection_claimed_events.worker_id` が空でないこと
- 後に述べる予定の表の `state` が `pending` か `succeeded` であること

外部キーは次のとおりに張る。

- `follows.follower_user_id` と `follows.followee_user_id` から `users.user_id` へ。`users` と `follows` は、要件が決めた単一の一次データのデータベースにある。
- `follow_base_events.follow_id` から `follows` へ。
- 二つの詳細イベントの `event_id` から基底イベントへ。
- 要求の `source_event_id` から基底イベントへ。
- 回収と成功の `request_id` から要求へ。
- 成功の `claim_id` から回収へ。

`followee_user_id` の外部キー違反（`23503`）は「登録されていない利用者をフォローする」に変換する。初期リリースには利用者の削除と更新が無いので、外部キーの確認で `users` の行に掛かる KEY SHARE のロックが待ちを生むことはない。

## 物理化の方針

### 物理写像: フォロー中の人数

読み取りを速くするため、`users_follow_counts (user_id, following_count)` の表を置き、フォローするたびに一つ増やし、外すたびに一つ減らす。

### 物理写像: フォローの状態と版

コマンドデータモデルは、`follows` の `status` と `current_version` を、楽観ロックとフォローできるかの判断のために妥協として持っている。物理でも同じ列を持ち、`status` は `text`、`current_version` は `bigint` にする。

一次データは基底イベントと詳細イベントである。状態を変えるたびに、基底イベントと詳細イベントの追加と、読んだ版を条件にした `follows` の更新を同じトランザクションで確定する。片方だけをコミットしない。こうすれば、`current_version` はそのフォローの基底イベントの最大の `version` と等しいままになる。状態と版は、`follow_base_events` を `version` の順に畳み込めば作り直せる。作り直した結果との突き合わせは、Read-010 で求められたときに行う。

### 物理写像: 識別子と時刻

`follow_id`、`event_id`、`request_id`、`claim_id` は `uuid` 型にし、アプリケーション（Go）が UUIDv7 で採番する。PostgreSQL 17 には UUIDv7 を作る組み込み関数が無い。UUIDv7 にすると主キーの B-tree への追加が末尾に集まり、ページ分割が減ると推定している。ポストIDも API が UUIDv7 で採番すると要件にあるので（バックエンド要件「ホームタイムラインを見られる」）、ID の作り方を一つにそろえる。

`occurred_at` はすべて `timestamptz` にし、値はデータベースの `now()`（トランザクションの開始時刻）で入れる。一つのトランザクションの基底イベントと反映の要求は同じ時刻になり、コマンドデータモデルの BDD-001 の例と一致する。回収のリースが切れたかも、同じデータベースの時計で判定する。担い手ごとの時計のずれで二重に回収しないためである。

### 物理写像: 反映の要求の予定の表

反映の要求、回収、成功は削除しない（非機能要件「データの保持」）。3年で要求は約1億6,400万件たまるが、その中で反映待ちなのは、通常ごく一部だと推定している。成功の表とのアンチ結合で反映待ちを探すと、未完了が少なくても累計の件数とともに遅くなる。そこで、要求ごとに一行の派生の表 `follow_change_reflection_schedules` を物理側に置く。持つ列は次のとおりである。

- `request_id`: 主キー。要求への外部キー
- `requested_at`: 要求の `occurred_at` を写したもの
- `state`: `pending` か `succeeded`
- `next_claimable_at`: 次に回収できる時点
- `last_claim_version`: 最後の回収の `version`。回収が無ければ0

この表の値はどれも、要求、回収、成功のイベントから導ける。同期は三つのトランザクションで行う。

- 要求を積むトランザクション: `pending` の行を作る。`next_claimable_at` は要求の時刻、`last_claim_version` は0にする。
- 回収を積むトランザクション: `next_claimable_at` を回収の時刻の5分後にし、`last_claim_version` を1増やす。
- 成功を積むトランザクション: `state` を `succeeded` にする。

どれもイベントの追加と同じトランザクションなので、片方だけが確定することはない。食い違いを疑ったときは、表を空にして作り直せる。要求ごとに、成功があれば `succeeded` にし、無ければ `pending` にする。`last_claim_version` には回収の `version` の最大（無ければ0）を、`next_claimable_at` には最新の回収の `occurred_at` の5分後（回収が無ければ要求の時刻）を入れる。

反映し終えた行も消さずに残す。Outbox の記録を削除しないという要件にそろえるためである。反映待ちは、`state = 'pending'` の行だけを持つ部分 index で探す。この形は、利用規模と負荷モデルの「累積データ量」がポストの配信について合意した形（要求ごとの調停用の派生状態と、`pending` の行だけの次回時刻の索引）と同じである。フォローへの適用は仮置きで、根拠は未決に書いた。

撤去するときは、担い手の走査を Read-004 の代わりの形（要求と成功のアンチ結合）へ戻してから、表と index を消す。イベントの表は変えない。この表は業務の不変条件を持たない。回収の重複を最終的に拒むのは、回収の一意制約である。

5分というリースの長さは、コマンドデータモデルが仮に置いた値をそのまま使う。値を変えるときは、この表の更新式だけを変えればよい。

## index

index は、下の代表的な読み取り（Read-001 から Read-010）と、業務制約を支えるものだけを置く。`users_pkey` はアカウントの業務が持つ index で、Read-001 と Read-002 が使うが、この資料では定義しない。

| index | 対象 | 種類 | 支えるRead・更新 | 更新費用 | 検証状態 |
|---|---|---|---|---|---|
| `follows_pkey` | `follows (follow_id)` | B-tree主キー | Read-005、フォローとフォローを外す操作の版の条件付き更新 | 初めてのフォローで一エントリ。状態の変更は HOT にならないので、変更ごとに一エントリ増える | planned |
| `follows_follower_followee_key` | `follows (follower_user_id, followee_user_id) INCLUDE (status)` | B-tree一意・複合、INCLUDE付き | Read-001、Read-002、Read-003、Read-007 | 初めてのフォローで一エントリ。状態の変更ごとに一エントリ増える | planned |
| `follows_followee_following_idx` | `follows (followee_user_id, follower_user_id)`、`status = 'following'` の行だけ | B-tree複合・部分index | Read-008、Read-009 | フォローで追加、フォローを外すと対象外になる | planned |
| `follow_base_events_pkey` | `follow_base_events (event_id)` | B-tree主キー | Read-005 | 業務イベントごとに一エントリ | planned |
| `follow_base_events_follow_version_key` | `follow_base_events (follow_id, version)` | 一意制約が作るB-tree複合index | 状態の変更、Read-010 | 業務イベントごとに一エントリ | planned |
| `follow_followed_events_pkey` | `follow_followed_events (event_id)` | B-tree主キー | フォローした事実の追加 | フォローごとに一エントリ | planned |
| `follow_unfollowed_events_pkey` | `follow_unfollowed_events (event_id)` | B-tree主キー | フォローを外した事実の追加 | フォローを外すごとに一エントリ | planned |
| `follow_change_reflection_requested_events_pkey` | `follow_change_reflection_requested_events (request_id)` | B-tree主キー | Read-005 | 要求ごとに一エントリ | planned |
| `follow_change_reflection_requested_events_source_event_key` | `follow_change_reflection_requested_events (source_event_id)` | 一意制約が作るB-tree | 要求の追加 | 要求ごとに一エントリ | planned |
| `follow_change_reflection_claimed_events_pkey` | `follow_change_reflection_claimed_events (claim_id)` | B-tree主キー | 成功から回収への外部キーの確認 | 回収ごとに一エントリ | planned |
| `follow_change_reflection_claimed_events_request_version_key` | `follow_change_reflection_claimed_events (request_id, version)` | 一意制約が作るB-tree複合index | 回収の追加、作り直し | 回収ごとに一エントリ | planned |
| `follow_change_reflection_succeeded_events_pkey` | `follow_change_reflection_succeeded_events (request_id)` | B-tree主キー | 成功の追加（同じ要求の二件目を拒む）、作り直し | 成功ごとに一エントリ | planned |
| `follow_change_reflection_schedules_pkey` | `follow_change_reflection_schedules (request_id)` | B-tree主キー | 回収と成功のときの予定の更新 | 要求ごとに一エントリ。更新は HOT にならないことがある | planned |
| `follow_change_reflection_schedules_pending_idx` | `follow_change_reflection_schedules (next_claimable_at, request_id)`、`state = 'pending'` の行だけ | B-tree複合・部分index | Read-004、Read-006 | 要求で追加、回収で置き換え、成功で対象外になる | planned |

`follows_follower_followee_key` は、「同じフォロワーと相手のフォローは一つ」を守る index である。同時に、フォロワーから見た読み取りをすべて支える。先頭の列を `follower_user_id` にしたのは、Read-001、Read-002、Read-003、Read-007 がどれもフォロワーを決めてから読むからである。`status` を INCLUDE にしたので、フォロー中の人数を数える Read-002 と、フォロー中の相手を集める Read-007 は、テーブル本体を読まない index-only scan にできる見込みである。`status` を変えると HOT 更新にならず、index のエントリが増える。ただしフォロー変更は設計基準で2件/秒なので、増え方は小さい。フォロー中の行だけの部分 index を別に置く案は、index が一つ増えるわりに、読む行がフォローを外した行の分しか減らないので採らなかった。

`follows_followee_following_idx` は、ポストとホームタイムラインの配信が、相手（投稿者）から見たフォロワーを読むために置く。利用規模と負荷モデルの「累積データ量」が、フォロワーの範囲をフォロー中の `(followed_user_id, follower_user_id)` の複合 index で走査するとしている。この資料の列名では `(followee_user_id, follower_user_id)` にあたる。二列目を `follower_user_id` にしたので、範囲の先頭から利用者IDの順に500人ずつ読める。フォローを外した行は配信に使わないので、部分 index にして除いた。

`follow_change_reflection_schedules_pending_idx` は、反映待ちの要求を回収できる順に探すために置く。反映し終えた要求は index から外れるので、大きさは未完了の件数だけで決まり、累計の件数とともに大きくならない。

## トランザクションと分離レベル

分離レベルと、トランザクションの中で何回やり直すかは、この節が操作ごとに決める。実装は、ここで決めた指定をトランザクションへ渡すだけにし、自分で選ばない。反映先の Redis への書き込みは RDB の外の効果なので、どのトランザクションにも含めない。

### 分離性判断: フォローする（上限5,000人と二重のフォロー）

フォロー中が4,999人のフォロワーが、二人を同時にフォローする場面を考える。二つの操作はどちらも4,999人と数えてから別々の行を書くので、どちらも成功すると5,001人になる（書き込みスキュー）。無い行はロックできず、書く行も別なので、行の競合では防げない。人数の上限は一意制約でも排他制約でも表せない。そこで、フォローする操作（初めてのフォローと、またフォローする場合）を SERIALIZABLE で実行し、その中で次の順に読み書きする。

1. `users` で相手が登録済みかを読む。
2. `follows` で自分と相手の組の行を読む。
3. 自分のフォロー中の行を数える。
4. 次の二つのどちらかを行う。
   - 行が無ければ、`follows` の行を作る。
   - `not_following` の行があれば、読んだ版を条件に `following` へ更新する。
5. 基底イベント、詳細イベント、反映の要求、予定の行を追加する。

直列化の失敗（SQLSTATE `40001`）とデッドロック（`40P01`）のときは、トランザクションの中で最大3回、10〜50msの揺らぎを置いてやり直す。やり直すと数え直すので、5,000人と数えたら「フォロー上限に達している利用者がフォローする」を返す。3回を使い切ったら、状態を変えずに一時的な失敗として返し、利用者の再操作に任せる。

同じ組の初めてのフォローが同時に二つ進んだ場合は、一意制約が後の一方を拒む。SERIALIZABLE では、それが `23505` ではなく `40001` として届くことがある。そのときはやり直しで行を読み直し、「フォロー中の相手をフォローする」を返す。

SERIALIZABLE を採ると、フォロー中が多い利用者の行を数えるときに、述語ロックがページ単位からテーブル単位へ格上げされうる。格上げされると、無関係なフォロワーのフォローとのあいだにも偽の直列化失敗が起きる。フォロー変更は設計基準2件/秒、1秒バースト50件/秒で、同じ利用者のフォローは20回/分に制限されているので、再試行で吸収できると推定している。ただし実機では確かめていない。競合試験で3回を使い切る割合が0.1%を超えたら、フォロワーごとの助言ロック（`pg_advisory_xact_lock`）と READ COMMITTED の組み合わせへ移す。

フォロー中の人数の列を持つ案は採らなかった。導いた値をもう一つ持つことになり、フォローを外すたびに二か所を直すことになるからである。`users` の行をロックする案は、アカウントの業務の表を並行制御に使うので採らなかった。この二つの案と助言ロックは、未決に確定の条件と一緒に残した。確かめ方は「物理設計の完了条件」の競合試験である。

検証状態: planned

### 分離性判断: フォローを外す

同じフォローを同時に二回外す場面がある。分離レベルと再試行の回数は、実装で負荷を見ながら適切に選ぶ。

検証状態: planned

### 分離性判断: 反映の要求を回収する、反映し終える

リースが切れた同じ要求を、二つの担い手が同時に回収しようとする場面を考える。回収は READ COMMITTED の短いトランザクションで、次を行う。

- 予定の表を、`state = 'pending'` かつ `next_claimable_at <= now()` を条件に更新し、`last_claim_version` を1増やして返させる。
- 返った版で回収の行を積む。

後から来た担い手の更新は、先の更新のコミットを待ったあとで条件を評価し直すので、0件になる。0件なら何も積まず、次の要求へ進む。それでも同じ版の回収を積もうとすれば、回収の一意制約が `23505` で拒む。どちらの場合もやり直さない。反映先への書き込みは、このトランザクションを確定した後に外で行う。

成功を積むのも READ COMMITTED の短いトランザクションで、成功の行の追加と、予定の表を `succeeded` にする更新を行う。リースが切れた後に元の担い手が成功を積むと、次の担い手の成功と重なりうる。そのときは成功の主キーが二件目を `23505` で拒むので、後の一方は書かずに終える。反映そのものの重複は、反映先で無害化する（非機能要件「信頼性」）。

どちらの操作も、デッドロックのときだけトランザクションの中で最大3回やり直す。ロックを飛ばす読み取り（`SKIP LOCKED`）は既定では使わない。回収の衝突が多すぎると観測されたときに足す。

検証状態: planned

## パーティションと配置

初期は、8つの表のどれもパーティションに分けない。最も大きくなるのは反映の回収と基底イベントで、3年の累計はどちらも約1億6,400万行と推定している（回収は、要求一件につき1回以上）。そのため、B-tree の index で読める範囲と推定した。どれかの表が10億行を超えるか、autovacuum の凍結処理（anti-wraparound）が保守の時間に収まらないと観測されたら、`occurred_at` での範囲パーティションを見直す。この閾値は仮置きである。

読み取りの配置は、操作ごとに次のとおりにする。

- フォローとフォローを外す操作の読み取り（Read-002、Read-003）、反映の担い手の読み取り（Read-004、Read-005）: プライマリから読む。
- 利用者の一覧（Read-001）: プライマリから読むことを仮置きした。
- ポストとホームタイムラインの読み取り（Read-007 から Read-009）: 読み取り元はそれぞれの業務の物理設計が決める。

複製の遅れの影響は、基盤構成が決まってから確かめる。

## 容量・性能・運用

下の表の容量は、行の頭部を含めた推定で、実測ではない。3年分で、表とindexを合わせて約200GB前後と推定している。利用規模と負荷モデルはフォロー変更履歴の論理量を約42GBとしているが、そこに要求、回収、成功、予定の表、行の頭部、index を足した値である。

| 観点 | 前提・観測値 | 設計判断 | 確認方法・閾値 |
|---|---|---|---|
| データ量 | フォロー変更は15万件/日、3年で1億6,425万件（負荷モデルの仮定）。`follows` の行は、組の数なので最大でこの件数 | パーティションに分けない。削除も退避もしない | 実データを模した件数で、表と index の大きさを `pg_total_relation_size` で測る。10億行で分割を見直す |
| 主要な書込み | フォロー変更は設計基準2件/秒、1秒バースト50件/秒。一回で5〜6行を書き、`follows` を一行作るか更新する | SERIALIZABLE と最大3回のやり直し。index は業務制約と Read に要るものだけ | 競合試験で、`40001` の割合と、3回を使い切った割合を測る |
| 主要な読取り | 要件に応答時間の目標値は無い。Read-007 はフォロー中の相手を最大5,000件読み、Read-008 と Read-009 はフォロワーを最大1万件以上読む | INCLUDE と部分 index で index-only scan にする | `EXPLAIN (ANALYZE, BUFFERS)` で、ヒープを読まないこと（Heap Fetches が小さいこと）を確かめる |
| バックアップ | 要件は自動バックアップとポイントインタイムリカバリを求める。RPO と RTO は未定 | 業務イベントと Outbox の記録を一次データとして全部戻す。予定の表は作り直せる | 復旧の訓練で、予定の表を作り直し、反映待ちが再び回収されることを確かめる |
| 反映の滞留 | 5分進捗が無い要求は調停の対象になり、30分を超えたら構造化 Error ログに出す（非機能要件） | Read-006 で、未完了の件数と最古の経過時間を読む | 未完了の件数と最古の経過時間を観測する |

## 採用するRDB機能

### 機能: INCLUDE 付きの一意制約

`follows_follower_followee_key` で使う。組の一意性を守る index に `status` を載せれば、フォロー中の人数とフォロー中の相手を index だけで読める。一意にしない別の index を足す必要が無い。対象の版で実行計画を確かめてはいない。

- 利用可能な版: PostgreSQL 11 から
- 根拠: https://www.postgresql.org/docs/17/sql-createtable.html
- 検証状態: planned

### 機能: 部分 index

`follows_followee_following_idx` と `follow_change_reflection_schedules_pending_idx` で使う。フォローを外した行と反映し終えた要求を index から外し、累積しても index の大きさが対象の行の数だけで決まるようにする。

- 利用可能な版: 対象版で利用できる
- 根拠: https://www.postgresql.org/docs/17/indexes-partial.html
- 検証状態: planned

### 機能: SERIALIZABLE 分離レベル（Serializable Snapshot Isolation）

フォローする操作で、上限5,000人を守るために使う。述語ロックの格上げの閾値（`max_pred_locks_per_relation`、`max_pred_locks_per_page`、`max_pred_locks_per_transaction`）は、既定値のまま始める。偽の直列化失敗が多いときに、見直すか、助言ロックへ移る。

- 利用可能な版: PostgreSQL 9.1 から
- 根拠: https://www.postgresql.org/docs/17/transaction-iso.html
- 検証状態: verified

## 物理設計の完了条件

### 検証: 競合時の業務結果

PostgreSQL 17.6 の複数のセッションで、次の四つを交差して実行する。

- 同じ組の初めてのフォロー
- フォロー中が4,999人の利用者による二つのフォロー
- 同じフォローを二回外す
- 同じ要求の回収

コマンドデータモデルの BDD-005、BDD-006、BDD-007、BDD-011 が許さない結果が起きず、後の一方へこの資料で決めた業務の結果かやり直しを返せば合格である。あわせて、フォロー中が5,000人に近い利用者を複数含めて1秒バースト50件/秒を流し、3回を使い切る割合を測る。0.1%以下なら SERIALIZABLE を確定し、超えたら助言ロックへ移す。DBMS の版、分離レベル、制約、やり直しの方針が変われば見直す。実機での証拠はまだ無い。

- 状態: planned

### 検証: 代表的な読み取りの性能

Read-001 から Read-010 と、それを支える index について、3年分の件数と、フォロワー数の偏りを再現する。そのうえで、`EXPLAIN (ANALYZE, BUFFERS)` と繰り返しの計測を行う。計画に想定の index が使われ、Read-002、Read-007、Read-008 が index-only scan になることを確かめる。SLO は要件が未定なので、値が決まったら合否に加える。

- 状態: planned

### 検証: 予定の表の作り直し

予定の表を空にし、要求、回収、成功のイベントから作り直す。作り直した表の `pending` の行が、成功の無い要求と一致し、担い手が再び回収できれば合格である。

- 状態: planned

## 未決

- **上限5,000人の守り方（仮置き）**: SERIALIZABLE と、最大3回のやり直しを仮置きした。
  - 根拠: 件数の上限は書き込みスキューで、一意制約や排他制約では守れない。候補の順で、制約の次が SERIALIZABLE である。
  - 採らなかった案: フォロワーごとの助言ロックと READ COMMITTED、`users` の行のロック、フォロー中の人数の列。
  - 確定の条件: 競合試験で、3回を使い切る割合と、述語ロックの格上げが偽の失敗をどれだけ生むかが分かったとき。
- **反映待ちの探し方（仮置き）**: 要求ごとの予定の派生の表と部分 index を仮置きした。
  - 根拠: 利用規模と負荷モデルが、ポストの配信について同じ形を合意している。フォローへの適用は類推である。
  - 採らなかった案: 要求と成功のアンチ結合で探す案、`SKIP LOCKED` で候補を取り合う案。
  - 確定の条件: 実データの件数で、アンチ結合が累計に比例して遅くなることを実行計画で確かめたとき。
- **利用者の一覧の読み取り元（仮置き）**: プライマリを仮置きした。
  - 根拠: フォローした直後の本人に、自分のフォローを「フォローしていない」と見せないため。
  - 採らなかった案: 読み取りプール。
  - 確定の条件: 一覧の要求頻度と、読み取りの複製の遅れが分かったとき。
- **一覧の一回の件数と続きの読み方**: クエリデータモデルの未決を引き継ぐ。Read-001 は利用者ID の昇順で、前のページの最後の利用者IDより大きい行から読む形にしてある。LIMIT の値は API の契約で決まる。
- **パーティションの閾値**: 10億行という閾値は仮置きで、表の大きさと凍結処理の時間を実測して決める。
- **回収のリース5分**: コマンドデータモデルの仮説を写した。反映先の応答時間が分かれば確定する。
- **SLO**: すべての Read の SLO は、要件が応答時間の目標値を未定にしているので空けた（非機能要件「まだ決まっていないこと」）。負荷試験の段階で決まる。
- **基盤構成へ差し戻す事項**: 次の四つは、基盤構成で決まってからこの資料を見直す。
  - 本番の AlloyDB が PostgreSQL 17 とどこまで互換か（SERIALIZABLE の述語ロックの設定、部分 index、INCLUDE の扱いを含む）
  - 読み取りプールの複製の遅れ
  - バックアップの RPO と RTO
  - 接続プールの上限
- **公式資料の確認**: この実行では、採用機能の公式資料を開いて確かめられなかった。対象版の資料と実機で確かめたら、採用機能の根拠を更新する。

## 代表的な読み取り

Read には、クエリデータモデルが確かめた利用者の読み取りに加えて、書込みの中の判定、背景処理の走査、監視の集計、ほかの業務が `follows` を読む読み取りを載せた。どれも件数とともに遅くなるので、`follows` の index を決める根拠になる。SLO は要件が未定なので、すべて空けた。

| Read | 利用者 | 並び順と上限 | 鮮度と一貫性 | 想定件数 | SLO | 支えるindex |
|---|---|---|---|---|---|---|
| Read-001 | フォローする相手を探す利用者 | `user_id` の昇順。前のページの最後の `user_id` より後から、LIMIT は API の契約で決まる（未決） | プライマリから読む（仮置き） | 登録済み利用者の全件のうち、一ページ分 | 未決 | `users_pkey`、`follows_follower_followee_key` |
| Read-002 | フォローする操作（書込みの中の判定） | なし。組は最大1行、フォロー中は最大5,000行を数える | フォローを書くのと同じ SERIALIZABLE のトランザクションで読む | フォロワーあたり最大5,000行と、フォローを外した行 | 未決 | `users_pkey`、`follows_follower_followee_key` |
| Read-003 | フォローを外す操作（書込みの中の判定） | なし。最大1行 | 外すのと同じ READ COMMITTED のトランザクションで読む | 1行 | 未決 | `follows_follower_followee_key` |
| Read-004 | 反映の担い手（背景処理） | `next_claimable_at, request_id` の昇順。LIMIT は担い手の一回の処理数 | プライマリから読む | 反映待ちの要求だけ。累計は約1億6,400万件 | 未決 | `follow_change_reflection_schedules_pending_idx` |
| Read-005 | 反映の担い手（背景処理） | なし。要求一件 | プライマリから読む | 1行ずつ | 未決 | `follow_change_reflection_requested_events_pkey`、`follow_base_events_pkey`、`follows_pkey` |
| Read-006 | 運用担当者（監視） | なし（件数と最古の時刻、30分を超えた要求の一覧） | 遅れてよい | 反映待ちの要求だけ | 未決 | `follow_change_reflection_schedules_pending_idx` |
| Read-007 | ホームタイムラインの読み取りと作り直し（ホームタイムラインの業務） | なし。最大5,000行 | 読み取り元はホームタイムラインの業務の物理設計が決める | フォロワーあたり最大5,000行 | 未決 | `follows_follower_followee_key` |
| Read-008 | ポストの受付（ポストの業務、書込みの中の判定） | なし。1万件に達したら数えるのをやめる | ポストを書くのと同じトランザクションで読む | 投稿者あたりのフォロワー数。数えるのは最大1万件 | 未決 | `follows_followee_following_idx` |
| Read-009 | 配信の担い手（ポストの業務、背景処理） | `follower_user_id` の昇順。範囲の先頭から500件ずつ | プライマリから読む。読んだ後のフォロー変更は許す | 投稿者あたりのフォロワー全件 | 未決 | `follows_followee_following_idx` |
| Read-010 | 運用担当者（物理写像の点検、求められたとき） | `follow_id` ごと | プライマリから読む | 点検の対象のフォローの基底イベント | 未決 | `follow_base_events_follow_version_key`、`follows_pkey` |

Read-001 は、利用者がフォローする相手を選ぶための読み取りで、クエリデータモデルの BDD-001 と BDD-002 を実現する。`users` を `user_id` の昇順に読み、前のページの最後の `user_id` より大きい行から一ページ分を取る。次の条件で `follows` を左外部結合する。

- `follower_user_id` が探した本人
- `followee_user_id` がその利用者

区別の決め方は次のとおりである。

- `user_id` が本人と同じなら「本人」
- 結合した `status` が `following` なら「フォロー中」
- 行が無いか `not_following` なら「フォローしていない」

返すのは利用者IDと区別である。一覧を利用者ID順にするのは、バックエンド要件「フォローできる」の決まりである。

Read-002 は、フォローしてよいかを判断するための読み取りである。`users` で相手の `user_id` があるかを読み、`follows` で自分と相手の組の行を読む。そのうえで、`follower_user_id` が自分で `status = 'following'` の行を数える。数えるのは最大5,000行までで、5,000に達したら数えるのをやめてよい。結合はしない。返すのは、相手の有無、組の行の状態と版、フォロー中の人数である。

Read-003 は、フォローを外せるかを判断するための読み取りである。自分と相手の組の `follows` の行を読み、状態と版を返す。行が無いか `not_following` なら「フォローしていない相手のフォローを外す」を返す。

Read-004 は、反映の担い手が次に回収する要求を探す読み取りである。予定の表から、`state = 'pending'` かつ `next_claimable_at` が今以前の行を、回収できる時点の古い順に読む。返すのは要求と、次の回収の版（`last_claim_version` に1を足したもの）である。結合はしない。

Read-005 は、回収した要求を反映するために、誰の何の変化かを得る読み取りである。要求から `source_event_id` で基底イベントを結合し、さらに `follow_id` で `follows` を結合する。返すのは次の値である。

- フォロワー、相手
- 基底イベントの `event_type` と `version`
- `follows` のいまの `status` と `current_version`

いまの状態を一緒に返すのは、反映先が古い変化を現在のフォローと照らして拒めるようにするためである（バックエンド要件「成立した事実の説明と回復」）。

Read-006 は、非機能要件「運用性と観測」の、未発行の要求の件数と最古の経過時間を出すための読み取りである。予定の表の `pending` の行について、件数と、最も古い `requested_at` を数える。あわせて、`requested_at` が30分より前の行の要求IDと成立日時を返し、構造化 Error ログに出す。

Read-007 は、ホームタイムラインのクエリデータモデルの「ホームタイムラインを読む」が、読む本人のフォロー中の相手を得るための読み取りである。`follower_user_id` が読む本人で、`status = 'following'` の行の `followee_user_id` を返す。

Read-008 は、ポストのコマンドデータモデルが、受け付けた時点のフォロワー数で配信の経路を選ぶための読み取りである。`followee_user_id` が投稿者の、フォロー中の行を最大1万件まで数え、1万人以上かどうかを返す。

Read-009 は、ポストの配信の範囲を決めるときと、範囲の中を配るときの読み取りである。`followee_user_id` が投稿者の、フォロー中の行を、`follower_user_id` の昇順に、範囲の先頭の利用者ID以上から500件ずつ読む。返すのはフォロワーの利用者IDである。

Read-010 は、物理写像の点検のための読み取りである。点検するフォローについて、`follow_base_events` の最大の `version` とその `event_type` を読み、`follows` の `current_version` と `status` と突き合わせる。
