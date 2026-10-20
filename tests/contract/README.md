# tests/contract

`biyori-proposal.schema.json` は、biyori-hub の `schemas/biyori-proposal.schema.json`(契約 `biyori-proposal/1`)の**写し**。
このリポジトリのテストが、出力した提案を検査するためだけに置いている。**契約の正本はハブにあり、ここで変えない。**

- 写した元: biyori-hub の commit `c172548`(段階12 フェーズ1の終わり)。
- sha256(改行を LF にそろえた内容。git に入っている形): `babbdbf4f823fd59b7eb23ccb6be02d4c73b68303f18ad804eefb5126c294089`
- ハブの契約は項目の追加だけで変わる(削除・意味変更は版を上げる `/2`)。ハブ側が、取り込んだこのリポジトリの写しと自分の正本が一致するかを検査する(段階12 フェーズ3)。
