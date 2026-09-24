---
name: physical-design
description: 論理上の意味と不変条件を保ち、要求・負荷・品質・基盤制約・観測結果を特定RDB製品と版の物理写像、型、制約、index、transaction、配置、運用へ統合する内部判断。design-rdb-physicalとrevise-rdb-physicalが共有する。
---

# RDB物理設計の判断を統合する

読み終えると、論理モデルの正式な定義の意味を保ったまま、上流制約をRDB固有の実現へ写し、根拠、検証状態、見直し条件を持つ`rdb-physical-design`本文を作って検査できる。

## 入力

- `grounded_physical_inputs`: 事実、合意済み決定、仮説、未確認、観測結果へ分類済みの入力
- `logical_document_path`: 論理データモデルの正式な定義の絶対path
- `database_product` / `database_version`: 対象RDB製品と一つに定まる版
- 改訂時だけ`existing_physical_document_path`: 既存物理設計の正式な定義の絶対path

入力に含まれる要求・負荷・品質・基盤・証拠は、それぞれの正式な定義を変更せず設計根拠として使う。

## 判断基準

| 観察対象 | 述語 | 行動 |
|---|---|---|
| 論理要素と物理構造 | 物理構造が同じ業務意味と不変条件を保存する | 型、技術列、派生表、冗長化、materialized view、partitionを選べる。各写像に一次データ、同期、再構築、撤去方法を書く |
| 追加構造 | 追加により業務意味・多重度・不変条件が変わる | 物理側へ入れず、論理側への差し戻し事項にする |
| 値域のCHECK | その値を検証する書き手がドメインモデルだけである | 置かない。技術処理のテーブルと、ドメインモデルの外から書かれる表にだけ置く（[物理写像と所有境界](references/physical-mapping.md)） |
| Readとindex | 利用者と目的、条件、join、order、limit、鮮度、件数、SLOまたは制約根拠を持つ | Readを先に記録し、そのReadまたは制約を支えるindexだけを採用する。Readには利用者の問い合わせだけでなく、背景処理の回収と走査（技術処理のライフサイクルで回収できる要求を探す読み取り）、監視の集計、条件付き書き込みの判定条件（`INSERT … SELECT … WHERE [NOT] EXISTS`や件数の確認）を含める。これらは利用者から見えないが、件数とともに遅くなる読み取りだからである |
| transaction | 論理データモデルの「並行実行で必要な保証」に、同時に進む操作と許してはいけない結果が具体化されている | 操作ごとに、対象版の分離レベル、制約、lock、競合検出と、再試行する失敗の種類と回数を決める。分離レベルと再試行の持ち主はこの物理設計であり、実装はここで決めた指定を渡すだけにする。名称だけでは完了にしない |
| 配置・replication | 上流基盤構成が指定されている | replicaの鮮度、failover中のwrite、同期・非同期、backup/recoveryがDB保証へ与える影響を書く。全体構成は選び直さない |
| 製品機能 | 対象版の公式仕様または実機結果へ到達できる | 採用する。記憶や別製品の類似機能しか無ければ代替または未決にする |
| 性能・競合・復旧の主張 | 対応する実機証拠がある | `verified`として書く。仕様・推定・机上検討だけなら`planned`として検証方法と見直し条件を書く |

判断時は[物理写像と所有境界](references/physical-mapping.md)、同時実行を扱うときは[transaction isolation](references/transaction-isolation.md)、保持・移行・復旧・観測を扱うときは[relational data lifecycle](references/relational-data-lifecycle.md)を全文読む。

## 手順

1. `python3 scripts/physical_design.py fingerprint --model-file <論理モデルの正式な定義の絶対path>`を実行し、論理構造の指紋を得る。終了code 0以外なら本文を作らない。
2. 上流の基準資料と証拠を読み、対象と論理設計に各入力pathと根拠状態を記録する。入力が無い関心は`なし`ではなく、非該当か未決かを理由つきで分ける。
3. 業務制約を物理制約へ写し、物理写像、型と時刻、Read、index、transaction、partitionと配置、容量・性能・運用、採用機能を決める。論理表との1対1対応は要求しない。
4. 各判断に根拠、検証状態（`verified`または`planned`）、検証方法、見直し条件を結び付ける。実機証拠が無い判断を`verified`にしない。
5. `write-doc`の`rdb-physical-design`型が定める節構成で完成本文を作る。BDDや論理テーブル定義は複製せず、論理モデルの正式な定義と指紋を参照する。
6. 完成本文を標準入力で`python3 scripts/physical_design.py check --model-file <論理モデルの正式な定義の絶対path> --product <製品> --version <版>`へ渡す。終了code 0は構造契約への適合、1は`problem`診断、2は入力を読めないことを示す。1なら本文を直して再検査し、2または解消不能なら止まる。

## 停止条件

**止まる。** 論理モデルの正式な定義を読めない、対象製品・版が空、toolが失敗する、物理実現に論理意味または不変条件の変更が必要な場合である。差し戻す論理変更、その根拠、物理側で代替できない理由を返す。

**仮説を明示して進む。** 上流値や実測が不足する、複数案が成立する場合は、仮説、根拠、採らなかった案、検証方法、見直し条件を本文へ残す。

## 出力

- `physical_final_markdown`
- `physical_validation_report`
- `status`: 未決や`planned`が残らなければ`ready`、残れば`unresolved`
- 論理側または基盤側への差し戻し事項
