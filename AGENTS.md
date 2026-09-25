> 作業を始める前に、workspace規約入口 `/Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/AGENTS.md` を読み、そこから指定される共通規約とこのrepository固有の規則を適用する。

# AGENTS.md

このrepositoryは、確定済みの論理データモデルと、要求・利用負荷・品質要求・基盤制約・観測結果を統合し、特定のRDB製品と版に対する物理設計を作成・改訂するsourceである。

- marketplaceへ公開するインストール対象は`rdb-design` package 1件だけにする。
- package manifestは`design-rdb-physical`と`revise-rdb-physical`の自己完結skill 2件を直接公開する。初回作成と既存の物理設計資料の改訂は、独立して依頼・完了できる仕事として分ける。
- 2入口が共有する、論理上の意味と不変条件を保ちながら物理写像・型・制約・index・トランザクション・配置・運用を決める判断は、内部skill `physical-design`が所有する。
- 論理データモデル、要求、利用・負荷モデル、品質要求、基盤構成は入力の基準資料として読み、変更しない。論理上の意味または業務不変条件の変更が必要なら、変更案と理由を返してその資料の持ち主へ戻す。
- 技術列、派生表、冗長化、materialized view、partitionなど、業務意味を変えない物理写像は物理設計に置ける。論理表との1対1対応を要求しない。一次データ、同期、再構築、撤去方法を明示する。
- HA/DR、cloud service、network、computeの全体構成は所有しない。入力された基盤構成がRDBの整合性、Read鮮度、transaction、復旧へ与える影響だけを扱う。
- 実機測定が無い設計判断を実証済みにしない。公式仕様に基づく設計、仮説、実機で確認済みの結果を区別し、未実測なら検証計画と見直し条件を残す。
- 資料のtemplateを持たない。成果物の節構成は、保存に使う`write-doc`の`rdb-physical-design`型が所有する。検査が読む目印は`write-doc`の公開契約の「検査が読む目印」が所有し、`physical_design.py`はそれだけを読む。見出しの文言は読まない。
- 利用者へ問う場面は公開playbook `grill`へ委ね、資料の保存は公開playbook `write-doc`へ委ねる。外部packageの内部実装を参照しない。
- install cache、隣接repository、利用者の資料、外部環境を直接変更しない。このsource treeだけを編集する。
- 変更後は`bash scripts/validate.sh`と、workspace rootの`bash scripts/validate.sh <このrepositoryの絶対path>`を実行する。

## 検査スクリプトは、意味が一意に決まることだけを判定する

このrepositoryの検査スクリプト（validate、lint、verify、checkなど、名前を問わない）が判定してよいのは、ファイルや見出しの有無、識別子や版の一致、宣言と配置の対応、禁止された書き方の有無のように、入力と基準資料から意味が決定論的に一意に決まることだけである。読んで解釈しないと決まらないことや、件数や語の出現のような品質の代わりの指標は判定せず、エージェントが読んで評価する（意味評価）。判定が一意に決まることを宣言できない検査は作らず、詳しい条件は `/Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/.agents/rules/deterministic-validation.md` に従う。
