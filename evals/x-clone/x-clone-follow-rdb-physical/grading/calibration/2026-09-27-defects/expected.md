# 期待する判定

この較正の資料は、2026-09-27-run1 の資料に、既知の欠陥を四つ埋めた写しである。grill の記録は元のままである。判定は欠陥の作り方から決まり、埋めていない条件は run1 の期待と同じにした。

一つ目は、業務の表の `status` に値域の CHECK を置くと書き換えた。二つ目は、フォロー中の人数の表 `users_follow_counts` を、導く元、失敗時の扱い、作り直し、外し方を書かずに足した。三つ目は、フォローを外す操作の分離レベルと再試行を「実装で適切に選ぶ」に書き換えた。四つ目は、実機の証拠が無いまま SERIALIZABLE の機能の検証状態を verified にした。

採点役には、このファイルを読ませない。

## 判定

- meaning-send-back: PASS（境目）
- meaning-derived-values: FAIL
- meaning-constraint-mapping: PASS
- meaning-check-owner: FAIL
- isolation-per-operation: FAIL
- isolation-absence-rule: FAIL（境目）
- isolation-external-outside: PASS
- read-before-index: PASS
- read-query-meaning-kept: PASS
- evidence-planned: FAIL
- evidence-hypothesis-marked: FAIL
- owner-infra-out: PASS
- owner-no-copy: PASS
- ops-capacity: PASS
- grill-only-conclusion-changing: FAIL
- follow-limit-concurrency: FAIL
- follow-no-count-as-fact: FAIL
- follow-refollow-row: PASS

## 理由

isolation-absence-rule と follow-limit-concurrency は、上限の守り方の節は元のまま SERIALIZABLE で残るが、足した人数の表が導いた値としての説明を持たないので、条件の「集計の列…を採るなら…書いている」に当たるかで読み方が分かれる。follow-limit-concurrency は FAIL の文に直接当たるので FAIL、isolation-absence-rule は人数の表を上限の守り方として採ったとは書いていないので境目とした。
