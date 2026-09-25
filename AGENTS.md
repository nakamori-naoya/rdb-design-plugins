> 共通の規約は /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/AGENTS.md にある。ここには、この repository だけの規則を置く。

# AGENTS.md

このrepositoryは、確定済みのコマンドデータモデルとクエリデータモデルと、要求・利用負荷・品質要求・基盤制約・観測結果を統合し、特定のRDB製品と版に対する物理設計を作成・改訂するsourceである。

- marketplaceへ公開するインストール対象は`rdb-design` package 1件だけにする。
- 公開入口は`design-rdb-physical`一つで、初回の作成と既存の物理設計資料の見直しを同じ入口で行う。内部skillは置かない。
- コマンドデータモデル、クエリデータモデル、要求、利用・負荷モデル、品質要求、基盤構成は入力の資料として読み、変更しない。データモデル上の意味または業務不変条件の変更が必要なら、変更案と理由を返してその資料の持ち主へ戻す。
- 技術列、派生表、冗長化、materialized view、partitionなど、業務意味を変えない物理写像は物理設計に置ける。データモデルのテーブルとの1対1対応を要求しない。一次データ、同期、再構築、撤去方法を明示する。
- HA/DR、cloud service、network、computeの全体構成は所有しない。入力された基盤構成がRDBの整合性、Read鮮度、transaction、復旧へ与える影響だけを扱う。
- 実機測定が無い設計判断を実証済みにしない。公式仕様に基づく設計、仮説、実機で確認済みの結果を区別し、未実測なら検証計画と見直し条件を残す。
- 資料のtemplateを持たない。成果物の節構成は、保存に使う`write-doc`の`rdb-physical-design`型が所有する。検査が読む目印はその型のtemplateが持ち、`physical_design.py`はそれだけを読む。見出しの文言は読まない。
- 利用者へ問う場面は`grill`へ、資料の保存は`write-doc`へ委ねる。
