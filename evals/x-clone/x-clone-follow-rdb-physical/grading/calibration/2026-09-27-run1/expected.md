# 期待する判定

この較正の資料は、2026-09-27 の1回目の実行（claude plugin eval、`--runs 1 --ablation none`）で作られた `rdb-physical-design.md` と grill の記録である。下の判定は、eval を組んだ担当が資料、記録、データモデル、要件を読んで出したもので、採点役がこれを再現できるかで採点の形を確かめる。境目と書いた条件は、読み方で判定が分かれうるので、一致の数を別に数える。

採点役には、このファイルを読ませない。

## 判定

- meaning-send-back: PASS（境目）
- meaning-derived-values: PASS
- meaning-constraint-mapping: PASS
- meaning-check-owner: PASS
- isolation-per-operation: PASS
- isolation-absence-rule: PASS
- isolation-external-outside: PASS
- read-before-index: PASS
- read-query-meaning-kept: PASS
- evidence-planned: PASS
- evidence-hypothesis-marked: FAIL（境目）
- owner-infra-out: PASS
- owner-no-copy: PASS
- ops-capacity: PASS
- grill-only-conclusion-changing: FAIL
- follow-limit-concurrency: PASS
- follow-no-count-as-fact: PASS
- follow-refollow-row: PASS

## 理由

grill-only-conclusion-changing は、Q1 の答えが「依頼文の…という事実で決まる。…仮置きではない」とあり、渡した資料から決まることを問うているので FAIL とした。

meaning-send-back は、コマンドデータモデルへの差し戻しが無く、基盤構成への差し戻しだけが未決にある。コマンドデータモデルへの差し戻しが無いことを明示した文は無いが、業務の意味を変えた箇所も無いので PASS とし、無いことが「読み取れる」かで分かれるので境目とした。

meaning-derived-values は、要求ごとの予定の表に、導く元、同期、作り直し、外し方がそろっているので PASS とした。

evidence-hypothesis-marked は、最初は PASS と期待していた。採点役は3回とも、再試行の揺らぎ「10〜50ms」と助言ロックへ移る閾値「0.1%」が要件に無い具体値で、仮説の断りも根拠も無いと指摘した。資料を読み直すと指摘どおりなので、期待を FAIL に直した（期待の誤り）。
直した後の採点では、同じ資料に対して採点役の票が PASS FAIL PASS に割れた。値の断りが未決の「上限5,000人の守り方（仮置き）」で足りると読むかで分かれるので、境目とした。
