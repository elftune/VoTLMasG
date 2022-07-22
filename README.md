# VoTLMasG

## 概要

[VOICEVOX Engine](https://github.com/VOICEVOX/voicevox_engine)を利用してマストドンの自動読み上げを行うPythonプログラム`VoTLMas`のGUI版です。

## 変更点[最新]

「準備」から書いてある内容は古く、最新の更新が反映されていません。ここに書いてある内容が最新になります。

- マストドンは500文字までTOOTできますが、VOICEVOXは入力文字数が長いと落ちることがあります(以前のバージョンで、落ちた後にPCを再起動しないとアプリが起動しなくなったことがあるのでわりとナーバス)ので文字数制限をつけています。`main.py`の`class TootManager`の最上部にある`MAX_TOOT_LETTERS`をお好みにしてください(デフォ255)。
- 複数のサーバーで同じアカウントをフォロー(や購読)することで同じTOOTを何度もしゃべることのないように判定処理をつけていますが全く簡易判定なので、続けて(もしくは短時間内に)同じTOOTをすると無視されます。
- `main()`で`FLAG_SPEAK_ALL_ACCOUNT`を`True`にすれば全員が喋ります。ただし`init_mysettins3.json`で名前指定していない人は文章のみ喋ります。
- `main()`で`FLAG_TOOT_SPOILER_TEXT`を`True`にすればCW(いわゆる、たたむ)の内容もしゃべります。ネタバレを喰らわないようにするためには`False`を推奨
- `main()`で`FLAG_USE_FTL`と`FLAG_SPEAK_ALL_ACCOUNT`を`True`にすれば連合TLもしゃべります...が当然のことながら全く追い付かないのでキューが溜まりえらいことになると思います。連合はあらかじめ不要と思われるドメインを片っ端からブロックしておいて、自分のお気に入り数個程度のドメインで運用するのが良いと思います。英語の場合は内部辞書に単語がない場合、ひたすらアルファベット１文字ずつ喋るのでさらに時間がかかります。
- サーバーに負荷がかかったり様々な原因で時々エラーが発生します。たぶん動かなくなると思う（そういった場合に遭遇していない）ので、時々終了して再実行するスタンスが良いと思います。つけっぱなしで何日も運用、という用途は想定していません。


## 準備

- `init_mysettins.json.txt`をもとに`init_mysettins.json`を作成 (ログインID、パスワード、サーバー、5分ごとに表示するPNGファイルのフォルダ を記述するファイルなので取り扱いには注意。うっかりフォルダごと人に渡したりしないように)
- `init_mysettins3.json.txt`をもとに`init_mysettins3.json`をお好みにあわせて修正  
  誰をなんという名前で表示し、どのキャラ声で喋らせるか(キャラを指定しない場合は -1 と入力)  
  仕様変更により、ここで設定した人しか喋らないようにしました。これを設定しないと魅力が半減する(想像した声で喋らない、読みがおかしいことが多い、等)と思いますので、がんばって設定して下さい。

- main.pyでは`main()`の中で2つのサーバーを指定しています。1つでよいなら「2」は削除またはコメントアウトしてください。(1つにせよ2つにせよ、`init_mysettins.json`をこれに対応するように記述してください。)

```dotnetcli
  account_info1 = 'server_nickname_1'
  account_info2 = 'server_nickname_2'
  mastodon1 = TootManager(account_info1, FLAG_USE_LTL, FLAG_USE_FTL)
  mastodon2 = TootManager(account_info2, FLAG_USE_LTL, FLAG_USE_FTL)

```

- Python Ver. 3.x環境を構築してください。自分は`3.8.9`です。`pyenv`と`venv`環境を想定
- macの場合はおそらくそのままでは正常に動作しません。グラフィック用ライブラリの`tcl-tk`のバージョンが大抵の場合8.5.9であり、手動で8.6系に更新する必要あります(そのままでは文字が全く表示されないなど、実質使用できません)。ggって対応してください。
  [ここ](https://zenn.dev/spacegeek/articles/3f8db1ffcd401e)が役に立つと思います。
- `VOICEVOX`が起動していればしゃべります。起動していない場合は文字だけです。途中で起動すればそれ以降はしゃべります。

```python
# Python環境が構築されていること (pyenv local 3.8.9 とか)
python --version # ってやって Python 3.8.9 とか表示されることを確認すること

python -m venv .venv
source .venv/bin/activate # Windowsなら .venv/scripts/activate
pip install --upgrade pip

pip install -r requirements-mac.txt # macの場合
pip install -r requirements-windows.txt # windowsの場合
pip install -r requirements-wsl2.txt # WSL2の場合

# WSL2の場合は以下も(インストールされていなければ)
sudo apt-get -y install python3-tk

python main.py
```

## 注意点

- macでの運用を想定しています。Windowsではなんかエラーが出たりしますが日常環境がないのでほとんど検証していません。LinuxはWSL2(Ubuntu 20.04＋pulseaudio＋Xlaunch＋Linux版VOICEVOX)でちょろっと検証しました。
- 端末から`python main.py`で起動すると、初回は`OpenCV`ライブラリの読み込みのために非常に待たされます。しかし、いくらまってもウィンドウが何も表示されないことがあります。これ、当方では数回に一度は発生する症状ですが、その場合はCtrl-Cで止めて再度実行してください。
- 繰り返しますが、`init_mysettins3.json`で設定した人しかしゃべりませんのでご注意ください  
（名前はアルファベット列で非常に長くなる場合があるなどそのまま喋らせてもあまり効果的ではないため、手動で設定する前提です。特定のIDが並ぶのを公開するのはアレだと思うので作者が使用しているファイルは載せません）

```dotnetcli
id ---> @から始まるID。自分のサーバーと同じ場合でもフルで書いてください
sp ---> VOICEVOXのSpeakerID。2022/07/10時点で0〜20まで指定可能。VOICEVOXを起動した状態で
http://localhost:50021/speakers
により確認してください（古いバージョンだと少ない場合があります）。
name ---> 名前。Tootを喋る前に読み上げます。短い名前にしましょう。

replace_content の方は、置き換えたい単語とよみをひたすら書きます。サーバーごとの絵文字？(:xxx: のやつ)も指定できます。
```

- `png_folder`の設定があり、指定したフォルダにPNGファイルがある場合、５分ごとに時報をしゃべり、絵も変わります。PNGは正方形のものを強く推奨します。
- 初期状態だと`HTL`と通知(DM、リプ)のみ表示します
- Boost時のアイコンの並びは一般的なものと逆にしていります(BTされた方が小さいし、名前も出ない)
- 画像やURLなどは省略されます。あくまでも読み上げが主用途(Tickerのようなものです)のため、詳細を見たい場合はブラウザで確認してください。
- ぶっちゃけ流速の速いTLでは喋る時間が非常に長いのでかなりズレが生じるため、LTLましてやFTLには向きません。時報も割り込まないので時間帯によってはかなりずれるでしょう(これがイヤな場合は'FLAG_USE_CLOCK = False'にしておくとよいと思います)。基本的には、人数を限定したHTLでの運用を想定しています。
- 超絶手抜きなので不具合が多数あります。2つ以上のサーバーで運用する場合、Toot内容によっては複数回Tootされます(BTなど)
