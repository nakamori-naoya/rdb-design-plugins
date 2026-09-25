# Validation

`scripts/validate.sh`は、workspaceのplugin package構造契約、両marketplaceと両manifestのidentity、公開2入口と内部1skillの集合、playbookの依存と参照、入力path検査、同一path更新guard、物理設計本文検査の正例・反例・境界例を確認する。

物理設計の意味上の妥当性、indexや分離レベルの選択、負荷・品質・基盤制約の統合、仮説と実証の区別は、検査scriptの成功だけでなく、対象の資料とskill本文を読んで評価する。
