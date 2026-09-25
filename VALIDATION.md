# Validation

`scripts/validate.sh` は、workspace の plugin package 構造契約、両 marketplace と両 manifest の identity、公開入口が `design-rdb-physical` の一つだけであること、`physical_design.py` の self-test、write-doc の見本の論理データモデルと物理設計で業務制約と物理制約の名前が一対一に対応することを確かめる。

物理写像が業務の意味を保つか、index と Read、分離レベルと繰り返しの回数、検証状態が証拠に支えられているかは、検査ではなく、資料と SKILL.md を読んで評価する。
