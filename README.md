# RDB Design

コマンドデータモデル、クエリデータモデル、要求、利用負荷、品質要求、基盤制約、観測結果から、特定のRDB製品・版に対する物理設計を作成し、見直すClaude Code／Codex両対応plugin repositoryです。

## 公開skill

`design-rdb-physical` 一つで、物理設計資料を新しく作ることと、既存の物理設計を負荷の変化、競合、障害、実行計画、DBMS の版の変更で見直して同じ資料を更新することの両方を行う。

物理設計はデータモデルだけから導かない。要求、利用・負荷モデル、品質要求、基盤構成、実行計画・負荷試験・競合試験・運用観測を、存在する範囲で明示入力として受け取る。入力不足は仮説と未決として残し、実測していない保証を実証済みとは書かない。

物理都合の技術列、派生表、冗長化、materialized view、partitionは、業務意味と不変条件を保ち、一次データ・同期・再構築・撤去方法を説明できる場合に物理設計へ置ける。データモデル上の意味を変える必要がある場合は、コマンドデータモデルをこのpluginで変更せず差し戻す。

## 検証

```bash
bash /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/rdb-design-plugins/scripts/validate.sh
bash /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/scripts/validate.sh /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/rdb-design-plugins
```
