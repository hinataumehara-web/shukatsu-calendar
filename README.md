# shukatsu-calendar

就活サイトのエントリー締切を自動で収集し、Google カレンダーに登録するツール。

締切は各サイトのマイページに散らばっていて、見落とすと取り返しがつかない。
このツールは毎日決まった時刻に各サイトを巡回し、見つけた締切を
「3日前・前日に通知が来る終日予定」としてカレンダーに入れる。同じ予定は二度登録しない。

```
$ python3 main.py --dry-run
2026-04-17 12:00:01 [INFO] === type就活 開始 ===
2026-04-17 12:00:17 [INFO] type就活: ログイン完了
2026-04-17 12:00:22 [INFO] type就活: 22 件抽出
2026-04-17 12:00:22 [INFO] 合計 22 件の締切を検出
  2026-04-18  [type就活] 株式会社◯◯ / 【インターン締切】3days 仕事体験
  2026-04-21  [type就活] △△株式会社 / 【インターン締切】キャリア形成プログラム
2026-04-17 12:00:22 [INFO] dry-run のためカレンダーには書き込みませんでした
```

## 特徴

- **サイト追加に Python を書かなくてよい** — 対応サイトは `sites/*.yaml` の定義で表現する。
  ログイン手順・一覧ページ・締切行の見つけ方をすべて YAML に書けるので、
  サイトの HTML が変わったときも YAML を直すだけで済む
- **止まりにくい Google 認証** — サービスアカウント方式に対応。
  OAuth のリフレッシュトークン失効（同意画面が「テスト」のままだと7日で失効する）で
  ある日突然止まる問題を避けられる
- **`--dry-run`** — カレンダーに書き込まずに、何が登録されるかだけ確認できる
- **重複を登録しない** — 予定の説明欄に埋め込んだキーで判定するため、毎日実行してよい
- **認証情報をリポジトリに置かない設計** — ログイン情報は `.env`、Google の鍵は
  gitignore 済みのファイル。YAML にパスワードを直接書くと定義の読み込み時にエラーになる

## 仕組み

```
sites/*.yaml ──▶ GenericScraper ──▶ DeadlineEntry ──▶ CalendarClient ──▶ Google カレンダー
  サイト定義      Playwright で        締切1件を表す      重複を除いて登録
                  ログイン・巡回        データクラス
```

一覧ページの DOM 構造はサイトごとに大きく異なるが、**画面に表示されるテキストの並び**は
どのサイトでも「タイトル → 会社名 → 締切日」のように似た順序になる。
そこでこのツールは `body` のテキストを行に分解し、

1. 「締切行」を見つける（完全一致 / 正規表現 / キーワードのいずれかで判定）
2. その行または周辺から日付を読む
3. 数行前まで遡り、ノイズ行を除いた最後の候補を会社名、その1つ前をタイトルとする

という手順を取る。この3つのパラメータが `sites/*.yaml` に書かれている。

## セットアップ

### 1. 依存関係

```bash
git clone https://github.com/<your-account>/shukatsu-calendar.git
cd shukatsu-calendar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. サイトのログイン情報

```bash
cp .env.example .env
```

`.env` に各サイトのメールアドレスとパスワードを書く。変数名は `sites/*.yaml` の
`credentials.*_env` と対応している。使わないサイトは `sites/<slug>.yaml` の
`enabled: false` にしておけばよい。

### 3. Google カレンダーの認証（サービスアカウント方式・推奨）

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作り、
   **Google Calendar API** を有効化する
2. 「IAM と管理」→「サービス アカウント」→ サービスアカウントを作成（ロールの付与は不要）
3. 作成したアカウント →「キー」→「鍵を追加」→ **JSON** をダウンロードし、
   `service_account.json` としてリポジトリ直下に置く
4. サービスアカウントのメールアドレス（`...@....iam.gserviceaccount.com`）をコピーし、
   Google カレンダーの「設定と共有」→「特定のユーザーやグループと共有する」で
   **「予定の変更権限」** を与える
5. `cp config.example.yaml config.yaml` して `calendar_id` を自分のカレンダー ID にする

> **なぜサービスアカウントなのか**: OAuth のユーザー認証は、OAuth 同意画面が「テスト」
> ステータスのままだとリフレッシュトークンが発行から7日で失効し、`invalid_grant` で
> 静かに止まる。本番公開するにはプライバシーポリシー URL などの用意が必要で、
> 個人ツールには重い。サービスアカウントなら同意画面の設定自体が不要で、失効もしない。

> **通知について**: Google カレンダーの通知は「予定を作った人」ではなく「見る人」の
> 設定に紐づく。サービスアカウントが共有カレンダーに入れた予定には、`reminder_days` ではなく
> 閲覧者側のデフォルト通知が適用されることがある。確実に通知したい場合は専用カレンダーを作り、
> そのカレンダーの通知設定を「3日前」「前日」にしておくとよい。

### 4. 動作確認

```bash
python3 main.py --list-sites     # 定義されているサイトの一覧
python3 main.py --dry-run        # 書き込まずに検出結果だけ見る
python3 main.py                  # 実際にカレンダーへ登録
```

## 新しいサイトに対応する

`sites/example_site.yaml` がスキーマ全項目つきのテンプレート。これをコピーして書き換える。

```bash
cp sites/example_site.yaml sites/mynavi.yaml
```

締切行のパターンを調べるには調査ツールを使う。ログインして一覧ページを開き、
表示テキストを行番号つきで書き出す。

```bash
python3 tools/inspect_site.py mynavi --grep 締切
python3 tools/inspect_site.py mynavi --headed --no-login   # ブラウザを見ながら
```

出力を見て、締切を示す行の形（`締切` だけの行なのか `2026年5月21日まで` のような行なのか）と、
会社名がその何行前に出るかを確認し、YAML の `deadline` と `company` を調整する。
調整できたら `python3 main.py --site mynavi --dry-run` で確認する。

### 同梱のサイト定義

| slug | サイト | 状態 |
|---|---|---|
| `bizreach_campus` | ビズリーチ・キャンパス | 2026-04 動作確認 |
| `type_shukatsu` | type就活 | 2026-04 動作確認 |
| `gaishishukatsu` | 外資就活ドットコム | 要調整（0件しか取得できていない） |

サイト側の改修でセレクタは壊れる。動かなくなったら上の手順で YAML を直してほしい。

## 定期実行

### macOS (launchd)

`~/Library/LaunchAgents/com.shukatsu.calendar.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>          <string>com.shukatsu.calendar</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/shukatsu-calendar/.venv/bin/python3</string>
        <string>/path/to/shukatsu-calendar/main.py</string>
    </array>
    <key>WorkingDirectory</key> <string>/path/to/shukatsu-calendar</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>   <integer>8</integer>
        <key>Minute</key> <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>   <string>/path/to/shukatsu-calendar/launchd_stdout.log</string>
    <key>StandardErrorPath</key> <string>/path/to/shukatsu-calendar/launchd_stderr.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.shukatsu.calendar.plist
```

### Linux (cron)

```cron
0 8 * * * cd /path/to/shukatsu-calendar && .venv/bin/python3 main.py
```

**失敗に気づける仕組みを用意しておくこと。** 認証切れやセレクタ変更でこの手のツールは
静かに止まる。ログが増えていない日が続いていないか、たまに確認するとよい。

## ディレクトリ構成

```
├── main.py                  エントリポイント（--dry-run / --site / --list-sites）
├── engine/
│   ├── site_config.py       サイト定義 YAML の読み込みとバリデーション
│   ├── scraper.py           YAML どおりに動く汎用スクレイパー
│   ├── calendar_client.py   Google カレンダーへの登録・重複チェック
│   ├── dateparse.py         日本語の日付表記のパーサ
│   └── models.py            DeadlineEntry
├── sites/                   サイト定義（example_site.yaml がテンプレート）
├── tools/inspect_site.py    ページテキストを調べる調査ツール
└── tests/                   pytest（YAML 定義の検証と日付パーサのテスト）
```

## テスト

```bash
pip install pytest
pytest -q
```

同梱サイト定義が壊れていないこと、認証情報が YAML に混入していないことも検証している。

## セキュリティ

以下は `.gitignore` 済み。**間違ってもコミットしないこと。**

| ファイル | 中身 |
|---|---|
| `.env` | 各就活サイトのログイン情報 |
| `service_account.json` | Google の秘密鍵 |
| `credentials.json` / `token.json` | OAuth のクライアントシークレットとトークン |
| `config.yaml` | カレンダー ID（個人のメールアドレス） |
| `*.log` / `debug_*.png` / `inspect_*.txt` | 応募先の企業名など個人の就活状況 |

一度コミットしてしまった秘密情報は、履歴から消してもリモートに残る可能性がある。
その場合は速やかに該当パスワード・鍵を無効化して作り直すこと。

## 免責

- 本ツールは各サイトの公式なものではなく、いかなる形でも提携していない
- 自動アクセスやスクレイピングを禁じている場合がある。**利用前に必ず各サイトの利用規約を
  確認し、自己責任で使用すること**
- 抽出は画面テキストのヒューリスティックに基づくため、**取りこぼしや誤検出が起こりうる**。
  重要な締切は必ず公式サイトで確認すること
- 短時間に繰り返し実行せず、1日1回程度の実行にとどめること

## ライセンス

MIT License — [LICENSE](LICENSE) を参照。
