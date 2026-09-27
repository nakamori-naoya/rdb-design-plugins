# アカウントのクエリデータモデル

利用者がGoogleアカウントでログインしたとき、自分がどの利用者かを知る読み取りが、アカウントのコマンドデータモデルの外部の認証の識別子とのひも付けと利用者だけで実現できることを確かめる。新しいテーブルや列は要らない。本人確認で確かめた外部の認証の識別子から`user_authentication_subjects`の一行を選び、`users`と結び付ければ、業務知識が決めた表示対象（そのGoogleアカウントに結びついた利用者一人）を返せる。

## ひも付けと利用者だけを読む

| 読むテーブル | 持ち主の資料 |
|---|---|
| `user_authentication_subjects` | [アカウントのコマンドデータモデル](command-data-model.md) |
| `users` | [アカウントのコマンドデータモデル](command-data-model.md) |

### Googleアカウントでログインする

本人確認で確かめた外部の認証の識別子の発行元と識別子の組で、`user_authentication_subjects`から`issuer`と`subject`が一致する行を一つ選ぶ。その`user_id`で`users`の行を結び付け、利用者IDと、結びついたGoogleアカウントを返す。表示対象は一人だけなので並び順は無い。要求の中に書かれた利用者IDは、行を選ぶ条件に使わない。選べる行が無ければ何も返らず、その人は利用者として登録していないと分かる。

`users`の`google_account_id`で選ぶ読み方もあるが、初期リリースでは一人の利用者に外部の認証の識別子が一つだけひも付くので、どちらで選んでも返る利用者は同じである。どちらを使うかは表示対象を変えないので、この資料では決めない。

## 業務知識のBDDとの対応

| 業務知識のBDD | この資料のBDD |
|---|---|
| BDD-006 | BDD-001 |
| BDD-007 | BDD-002 |
| BDD-008 | 対象外 |
| BDD-009 | BDD-003 |

業務知識のBDD-008（LINEではログインできない）は、Googleアカウント以外の方法として本人確認の段階で拒まれ、データを読むところまで届かないので対象外にした。

## 未決

外部の認証の識別子の正確な項目（どの項目を`issuer`と`subject`に写すか）は、コマンドデータモデルと同じく要件自体が未決としている。確定しても、この資料の読み方と返る結果は変わらない。

## BDD

### [BDD-001] 登録したGoogleアカウントでログインすると、結びついた利用者一人が返る

```gherkin
Given: 利用者 U-0001 はGoogleアカウント G-1001 で登録しており、外部の認証の識別子は発行元 https://auth.example.com の sub-1001 である
  And: 利用者 U-0002 はGoogleアカウント G-2002 で登録しており、外部の認証の識別子は同じ発行元の sub-2002 である
When: Googleアカウント G-1001 の持ち主が、外部の認証の識別子 sub-1001 と確かめられて2026年10月5日 08:00にログインする
Then: 利用者 U-0001 だけが返る
  And: 利用者 U-0002 は返らない
```

#### データの状態

**Before**

**`user_authentication_subjects`**

| issuer | subject | user_id |
|---|---|---|
| https://auth.example.com | sub-1001 | U-0001 |
| https://auth.example.com | sub-2002 | U-0002 |

**`users`**

| user_id | google_account_id |
|---|---|
| U-0001 | G-1001 |
| U-0002 | G-2002 |

**取得結果**

| 利用者ID | Googleアカウント |
|---|---|
| U-0001 | G-1001 |

### [BDD-002] 登録していないGoogleアカウントでログインすると、何も返らない

```gherkin
Given: 利用者 U-0001 はGoogleアカウント G-1001 で登録しており、外部の認証の識別子は発行元 https://auth.example.com の sub-1001 である
  And: 利用希望者はGoogleアカウント G-4004 の持ち主として、外部の認証の識別子 sub-4004 と確かめられているが、利用者として登録していない
When: 利用希望者が2026年10月5日 09:00にGoogleアカウント G-4004 でログインする
Then: どの利用者も返らない
```

#### データの状態

**Before**

**`user_authentication_subjects`**

| issuer | subject | user_id |
|---|---|---|
| https://auth.example.com | sub-1001 | U-0001 |

**`users`**

| user_id | google_account_id |
|---|---|
| U-0001 | G-1001 |

**取得結果**

| 利用者ID | Googleアカウント |
|---|---|
| （行なし） | |

### [BDD-003] 他人の利用者IDを名乗ってログインしても、確かめたGoogleアカウントに結びついた利用者が返る

```gherkin
Given: 利用者 U-0001 はGoogleアカウント G-1001 で登録しており、外部の認証の識別子は発行元 https://auth.example.com の sub-1001 である
  And: 利用者 U-0002 はGoogleアカウント G-2002 で登録しており、外部の認証の識別子は同じ発行元の sub-2002 である
When: Googleアカウント G-2002 の持ち主が、外部の認証の識別子 sub-2002 と確かめられたうえで、利用者ID U-0001 を名乗って2026年10月5日 11:00にログインする
Then: 利用者 U-0002 が返る
  And: 名乗った利用者 U-0001 は返らない
```

#### データの状態

**Before**

**`user_authentication_subjects`**

| issuer | subject | user_id |
|---|---|---|
| https://auth.example.com | sub-1001 | U-0001 |
| https://auth.example.com | sub-2002 | U-0002 |

**`users`**

| user_id | google_account_id |
|---|---|
| U-0001 | G-1001 |
| U-0002 | G-2002 |

**取得結果**

| 利用者ID | Googleアカウント |
|---|---|
| U-0002 | G-2002 |
