# RDB Design

論理データモデル、要求、利用負荷、品質要求、基盤制約、観測結果から、特定のRDB製品・版に対する物理設計を作成・改訂するClaude Code／Codex両対応plugin repositoryです。

## 公開skill

| skill | 完了状態 |
|---|---|
| `design-rdb-physical` | 上流正本と対象RDB・版から、根拠と検証状態を持つ物理設計正本を新規作成する |
| `revise-rdb-physical` | 既存物理設計へ負荷変化、競合、障害、実行計画、DBMS変更を当て、同じ正本を更新する |

物理設計は論理モデルだけから導かない。要求、利用・負荷モデル、品質要求、基盤構成、実行計画・負荷試験・競合試験・運用観測を、存在する範囲で明示入力として受け取る。入力不足は仮説と未決として残し、実測していない保証を実証済みとは書かない。

物理都合の技術列、派生表、冗長化、materialized view、partitionは、業務意味と不変条件を保ち、正本・同期・再構築・撤去方法を説明できる場合に物理設計へ置ける。論理上の意味を変える必要がある場合は、論理正本をこのpluginで変更せず差し戻す。

## 検証

```bash
bash /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/rdb-design-plugins/scripts/validate.sh
bash /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/scripts/validate.sh /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/rdb-design-plugins
```
