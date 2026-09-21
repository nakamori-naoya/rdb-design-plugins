---
name: design-rdb-physical
description: 確定済みの論理データモデルと、要求・利用負荷・品質要求・基盤制約を入力に、特定RDB製品・版の型、物理制約、index、transaction、配置、運用を決め、根拠と検証状態を持つRDB物理設計の正式な定義を新規作成する。「RDB物理設計を作って」「PostgreSQL向けに物理化して」と言われたときに使う。
---

# RDB物理設計を作る

読み終えると、論理データモデルが定める業務意味と不変条件を保ち、要求、利用負荷、品質要求、基盤制約を対象RDB製品・版の実現方式へ写した物理設計資料を1本新規保存できる。論理モデルの正式な定義、品質閾値、負荷値、HA/DR構成はこの入口で作り直さない。

同じdirectoryの`playbook.yml`が工程順の定義である。手順に入る前に、同梱の内部skill `physical-design`の`SKILL.md`を読み、その判断規律とtool契約を全工程へ適用する。

## 入力

| 入力 | 内容 | 満たさないときの扱い |
|---|---|---|
| `user_input` | 設計対象、目的、既知の制約 | 対象が識別できなければ止まる |
| `logical_document_path` | 必須。確定済み論理データモデルの正式な定義の絶対path | 無い、相対path、読めない、symlinkなら止まる |
| `database_product` / `database_version` | 必須。対象RDB製品と一つに定まる版 | 無い、または版が範囲指定なら`settle-physical-inputs`で確かめ、決まらなければ止まる |
| `requirements_document_path` | 任意。要求の基準資料の絶対path | 無ければ要求由来の制約を仮説または未決として扱う |
| `workload_document_path` | 任意。件数、Read/Write比、peak、burst、growth、skew、hot keyを持つ利用・負荷モデルの基準資料の絶対path | 無ければ性能・容量・partition判断を実証済みにせず、仮説と検証計画を残す |
| `quality_document_path` | 任意。latency、throughput、availability、consistency、durability、recovery、costの品質要求の基準資料の絶対path | 無ければ対応する設計判断を仮説または未決にする |
| `architecture_document_path` | 任意。配置、replication、failover、backup、運用境界を持つ基盤構成の基準資料の絶対path | 無ければ全体構成を創作せず、RDB内で閉じる判断だけを確定する |
| `evidence_paths` | 任意。実行計画、benchmark、競合試験、復旧試験、運用観測の絶対path配列 | 空なら設計根拠と検証計画を残し、実証済みにしない |
| `references` | 任意。追加で従う資料の絶対path配列 | 相対path、読めないpath、symlinkがあれば止まる |
| `output_directory` / `name` | 新しい正式な定義を置く既存directoryの絶対pathと、path要素を含まない`.md`名 | 保存先が確認できない、または同名fileがあれば書かずに止まる |

## 判断基準

| 観察対象 | 述語 | 行動 |
|---|---|---|
| 設計入力 | 論理意味に加え、判断に関係する負荷・品質・基盤制約が根拠状態つきで読める | 確定事項・合意・仮説・未決を分けて設計へ使う。欠けた入力を業務の筋だけで確定値にしない |
| 物理上の追加構造 | 業務意味を変えず、一次データ、同期、再構築、撤去方法を説明できる | 技術列、派生表、冗長化、materialized view、partitionを物理写像として記録する。説明できなければ採用しない |
| 論理への影響 | 業務上の意味、関係、多重度、不変条件の変更が必要である | 物理側で補わず、必要な論理変更と根拠を返して止まる |
| 性能・容量の主張 | 実行計画または測定結果へ到達できる | 観測済みとして書く。仕様と推定だけなら仮説と検証計画として書く |
| HA/DRの論点 | 入力された基盤構成がDB整合性、Read鮮度、transaction、復旧へ影響する | 影響とDB側の実現・検証を設計する。全体のcloud構成選定は入力の所有者へ返す |

## 手順

1. **preflight-inputs（`scripts/input_paths.py`）。** path入力をJSONで標準入力へ渡す。終了code 0なら正規化済みpath一覧、1なら契約違反の診断、2なら入力を読めない。0以外なら外部playbookを呼ばずに止まる。
2. **settle-physical-inputs（`grill`）。** 調べても分からず、答えでDBMS・版、整合性、容量、配置、保存先が変わる問いだけを成果を左右する順に渡す。返った未決は推奨を仮説として保持する。2回目は利用者が求めた場合か、決定なしでは停止条件に当たる場合だけ呼ぶ。
3. **ground。** 全入力を、事実・合意済み決定・仮説・未確認・観測結果へ分け、各物理判断がどの入力に依存するかを保持する。
4. **design-and-verify（`physical-design`）。** 内部skillの判断規律で物理設計本文を組み立て、論理構造の指紋、上流の基準資料、物理写像、Readとindex、transaction、配置、容量・運用、採用機能、検証状態を記録し、決定論的toolの検査を通す。
5. **document（`write-doc`）。** 検査済み本文を`material: [{kind: text, content: <本文>}]`、`document_type: rdb-physical-design`、確認済みの`output_directory`と`name`、入力の`references`で保存する。`status: completed`かつ返却pathが指定先と一致した場合だけ完了する。

## 停止条件

**止まる。** 必須の論理モデルの正式な定義、対象RDB・版、保存先を確定できない、path入力が契約に反する、toolまたは外部playbookが失敗する、論理意味の変更が必要になる場合である。止まるときは書き込まず、確定済み範囲、止めた判断、必要な入力、再開条件を返す。

**仮説を明示して進む。** 負荷、品質、基盤、実測証拠の一部が無い、または複数の実現方式が成立する場合は、最も筋の良い案を仮説として採り、根拠、採らなかった案、検証計画、見直し条件を本文と未決へ残す。未実測の性能・競合・復旧を実証済みにはしない。

## 出力

- `physical_rdb_design_path`: 新規保存したRDB物理設計の正式な定義の絶対path
- `status`: 後続実装へ渡せる`ready`、または仮説・未決・未実測を含む`unresolved`
- 設計根拠に使った上流の基準資料、主要な物理写像、indexとtransaction判断、検証済み／未検証の範囲、論理側または基盤側へ返した事項の報告
