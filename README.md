# VoTLMasG

## 概要

[VOICEVOX Engine](https://github.com/VOICEVOX/voicevox_engine)を利用してマストドンの自動読み上げを行うPythonプログラム`VoTLMas`のGUI版です。

## 準備

- `init_mysettins.json.txt`をもとに`init_mysettins.json`を作成 (ログインID、パスワード、サーバー、5分ごとに表示するPNGファイルのフォルダ を記述するファイルなので取り扱いには注意。うっかりフォルダごと人に渡したりしないように)
- `init_mysettins3.json.txt`をもとに`init_mysettins3.json`をお好みにあわせて修正 (誰を、なんという名前で表示し、どのキャラ声で喋らせるか。指定しない場合は -1 と入力)
これを設定しないと魅力が半減する(名前を喋らない、指定した声で喋らない、読みがおかしいことが多い、等)と思いますので、がんばって設定して下さい。
- Python Ver. 3.x環境を構築してください。自分は`3.8.9`です。`pyenv`と`venv`環境を想定
- macの場合はおそらくそのままでは正常に動作しません。グラフィック用ライブラリの`tcl-tk`のバージョンが大抵の場合8.5.9であり、手動で8.6系に更新する必要あります(そのままでは文字が全く表示されないなど、実質使用できません)。ggって対応してください。
  [ここ](https://zenn.dev/spacegeek/articles/3f8db1ffcd401e)が役に立つと思います。
- `VOICEVOX`が起動していればしゃべります。起動していない場合は文字だけです。途中で起動すればそれ以降はしゃべります。
- 「tcl-tkのインストールや更新がうまくいかない」「画像は不要、文字＋しゃべりだけでいい」という場合は下記で`main.py`ではなく`mainc.py`をご使用ください。

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

python main.py # GUI版
python mainc.py # CUI版
```

## 注意点

- macでの運用を想定しています。Windowsではなんかエラーが出たりしますが日常環境がないのでほとんど検証していません。LinuxはWSL2(Ubuntu 20.04＋pulseaudio＋Xlaunch＋Linux版VOICEVOX)でちょろっと検証しました。
- 端末から`python main.py`で起動すると、初回は`OpenCV`ライブラリの読み込みのために非常に待たされます。しかし、いくらまってもウィンドウが何も表示されないことがあります。これ、当方では数回に一度は発生する症状ですが、その場合はCtrl-Cで止めて再度実行してください。
- 繰り返しますが、`init_mysettins3.json`でIDと名前などの対応づけをしないと名前をしゃべりませんのでご注意ください  
（名前はアルファベット列で非常に長くなる場合があるなどそのまま喋らせてもあまり効果的ではないため、手動で設定する前提です。特定のIDが並ぶのを公開するのはアレだと思うので作者が使用しているファイルは載せません）

```dotnetcli
id ---> @から始まるID。自分のサーバーと同じ場合でもフルで書いてください
sp ---> VOICEVOXのSpeakerID。2022/07/10時点で0〜20まで指定可能。VOICEVOXを起動した状態で
http://localhost:50021/speakers
により確認してください（古いバージョンだと少ない場合があります）。
name ---> 名前。Tootを喋る前に読み上げます。短い名前にしましょう。

replace_content の方は、置き換えたい単語とよみをひたすら書きます。サーバーごとの絵文字？(:xxx: のやつ)も指定できます。
```

- `png_folder`の設定があり、指定したフォルダにPNGファイルがある場合、５分ごとに時報をしゃべり、絵も変わります。PNGは正方形のものを強く推奨します。これが不要な場合、`png_folder`を設定しないか'FLAG_USE_CLOCK = False'にしてください。
- 初期状態だと`HTL`と通知(DM、リプ)のみ表示します
- Boost時のアイコンの並びは一般的なものと逆にしていります(BTされた方が小さいし、名前も出ない)
- 画像やURLなどは省略されます。あくまでも読み上げが主用途(Tickerのようなものです)のため、詳細を見たい場合はブラウザで確認してください。
- ぶっちゃけ流速の速いTLでは喋る時間が非常に長いのでかなりズレが生じるため、LTLましてやFTLには向きません。時報も割り込まないので時間帯によってはかなりずれるでしょう(これがイヤな場合は'FLAG_USE_CLOCK = False'にしておくとよいと思います)。基本的には、人数を限定したHTLでの運用を想定しています。
