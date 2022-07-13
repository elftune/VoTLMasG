import base64
from io import BytesIO
import os
from pkgutil import get_data
import queue
import random
import tempfile
from urllib.parse import uses_relative
from pytz import timezone
import requests
import pathlib
import time
import datetime
from lib2to3.pytree import convert
import re, os, json, requests
from time import sleep
import datetime
import threading
import queue
from dateutil import tz
import glob
import copy

from PIL import Image, ImageTk
import cv2
import PySimpleGUI as sg
import demoji

from mastodonEx import MastodonEx, StreamListenerEx
import UseVV


# フラグ (HTLと通知は強制)
FLAG_USE_LTL = True # ローカル。fedibirdのようにLTLがない場合はFalseに
FLAG_USE_FTL = False # 連合 (大量に流れるので片っ端からdomain_blockしてからでないと実用的ではないと思う)
FLAG_USE_CLOCK = True

appname = 'VoTLMasG'
# init_mysettings.json の中でログインするIDごとにつけてください(英数字)
# サーバー ＋ ニックネーム がわかりやすくてよいでしょう
account_info = 'server_nickname'

cid_file = 'file_cid_' + account_info + '.txt'
token_file = 'file_access_token_' + account_info + '.txt'
FILE_SETTINGS_1 = 'init_mysettings.json'
FILE_SETTINGS_2 = 'init_mysettings3.json'
JST = tz.gettz('Asia/Tokyo') # お好みで
weekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] # 月曜から
q1 = queue.Queue() # Toot表示用
q2 = queue.Queue() # Toot再生用
replace_id2name = [] # IDを名前に変換
replace_content = [] # ちゃんと読ませたい単語用
lock = threading.Lock()

png_folder = ''
png_files = []
ICON_W_H= 100 # アイコンサイズ
ICON_W_H_2= 32 # BTアイコンのサイズ
WAV_PLAYING = False
mastodon = None
listener = None
useVV = None
prev_toot_id = -1

class GL_data():
  toot_id = -1
  name = ''
  toot_text = ''
  img_avatar = None
  img_boosted_avatar = None

g_data = GL_data()


def imread_web(url):
    res = requests.get(url)
    img = None
    
    # 本来はこう書くのだが、Windowsではcloseしないと読めないらしいwww
    if os.name != 'nt':
      with tempfile.NamedTemporaryFile() as fp:
          fp.write(res.content)
          fp.file.seek(0)
          img = cv2.imread(fp.name)
    else:
      fp = tempfile.NamedTemporaryFile(delete=False)
      fp.write(res.content)
      fp.file.seek(0)
      fp.close()
      img = cv2.imread(fp.name)
      os.remove(fp.name)
    return img
  
def pil_to_base64(img, format="png"):
    buffer = BytesIO()
    img.save(buffer, format)
    img_str = base64.b64encode(buffer.getvalue()).decode("ascii")
    return img_str

def cv_to_base64(img):
    _, encoded = cv2.imencode(".png", img)
    img_str = base64.b64encode(encoded).decode("ascii")
    return img_str

def remove_emoji(src_str):
    return demoji.replace(string=src_str, repl="")

def init():
  global convURL, conv, convp, url, png_folder, png_files
  global replace_id2name, replace_content, account_info

  print("初期化開始")

  # ログイン情報
  try:
    json_open = open(FILE_SETTINGS_1, 'r', encoding='UTF-8')
  except:
    print(f"ERROR: {FILE_SETTINGS_1} が準備できていません。READMEを確認ください。")
    exit()

  try:  
    json_load = json.load(json_open)
    url = json_load[account_info]['url']
    if url[0:8] != "https://":
      print("ERROR: https:// からアドレスが始まるWebサイトのみ対応です。") # これ以降で先頭8文字が"https://"前提のところがあるので
      exit()
    email = json_load[account_info]['user_id']
    password = json_load[account_info]['password']
    png_folder= json_load[account_info]['png_folder']
    if png_folder[-1] == '/' or png_folder[-1] == '\\':
      png_folder = png_folder[0:len(png_folder)-1] 
    png_files = glob.glob(png_folder + "/*.png")
    if len(png_files) == 0:
      print(f"{png_folder} にPNGファイルが存在しないため、時刻読み上げ機能は使用しません。")
      FLAG_USE_CLOCK = False
          
  except:
    print(f"ERROR: {FILE_SETTINGS_1} の内容が適切ではありません。READMEを確認ください。")
    exit()
  
  # 文字列置換情報
  json_open = None
  try:
    json_open = open(FILE_SETTINGS_2, 'r', encoding='UTF-8')
  except:
    print(f"{FILE_SETTINGS_2} が存在しないため名前をしゃべりません。また、単語変換もないため不自然な発声が多くなります。\nREADMEを確認し、{FILE_SETTINGS_2}を設定されることをお勧めします。")

  if json_open != None:
    try:
      json_load = json.load(json_open)
      replace_id2name = json_load['replace_id2name']
      replace_content = json_load['replace_content']
    except:
      print(f"ERROR: {FILE_SETTINGS_2} の内容が適切ではありません。READMEを確認ください。")
      exit()


  # 初回起動時など'client_id.txt' が未作成の場合 ('access_token.txt'もないだろうから作る)
  try:
    if os.path.isfile(cid_file) == False:
      MastodonEx.create_app( appname, api_base_url = url, to_file = cid_file )
      mastodon = MastodonEx( client_id = cid_file, api_base_url = url, )
      mastodon.log_in( username = email, password = password, to_file = token_file )
    else:
      mastodon = MastodonEx( client_id=cid_file, access_token=token_file, api_base_url=url )
  except:
    print(f"ERROR: {FILE_SETTINGS_1} の内容が適切ではありません。READMEを確認ください。")
    exit()

  # GETで得られるデータで本文(content)には <p></p>がだいたいついているので消すための準備
  conv = re.compile(r"<[^>]*?>")
  # URLは喋らせると長いので丸ごと消すための準備
  convURL = re.compile(r"(https?|ftp)(:\/\/[-_\.!~*\'()a-zA-Z0-9;\/?:\@&=\+\$,%#]+)")


  # 欧米圏はスキップさせたい（膨大に増えるので）　中韓はしゃーない
  # \u200Bは半角スペースの幅なし？
  convp = re.compile('[a-zA-Z0-9!\"“#$%\&\'’()=\-~|¥\]+`@\{\}*;:<>?,./_。 \n\u200B]+')
  print("初期化完了\n")
  return mastodon

def do_1toot(toots):
  global convURL, conv, convp, url, useVV
  global replace_id2name, replace_content

  # 同じサーバーの場合はドメイン名が省略されるので足し、domain=xxxx.xxの形にする
  s = toots['account']['acct'] # 'gummykirby@dragon-fly.club'
  idx = s.find('@')
  if idx >= 0:
    domain = s[idx + 1:] # dragon-fly.club
  else:
    s = toots['account']['url'] # 'https://mstdn.jp/@mamemimu'
    s = s[8:]
    domain = s[:s.find('/')] # mstdn.jp

  # toot_text --> 喋る内容
  # 改行は明確に区切らないと不自然になるので 。 にする
  toot_text = toots['content']

  if toots['spoiler_text'] != '':
    toot_text = toots['spoiler_text'] + " 。[たたむ]。 " + toot_text

  toot_text = toot_text.replace('\n', '。')
  toot_text = toot_text.replace('<br />', '。')
  toot_text = toot_text.replace('<br>', '。')
  toot_text = conv.sub("", toot_text) # <x>xxxxx</x>  を全て抽出

  toot_text0 = toot_text
  
  # emoji除去
  toot_text = remove_emoji(toot_text)

  # 単純に <a href移行を削除すると、リプがダメになる！
  # @u32 てすと　は、
  # '<p><span class="h-card"><a href="https://fedibird.com/@u32" class="u-url mention">@<span>u32</span></a></span> てすと</p>'
  # '<'と'>'の一式(中身を含む)を片っ端から削除する

  if toot_text.find('http') >= 0: # URLは長いのでしゃべりは省略
    toot_text = convURL.sub("", toot_text)
    toot_text += "。URLあり"

  toot_text = toot_text.lower()

  for txt in replace_content:
    if txt in toot_text:
      toot_text = toot_text.replace(txt, replace_content[txt])

  
  if toots['media_attachments'] != []:
    toot_text += "。メディアあり"
    toot_text0 += " メディアあり"

  if len(toot_text) > 255:
    toot_text = toot_text[:255] + "。以下略"
    toot_text = toot_text0[:255] + "。以下略"
    
  if toot_text == '' or toot_text == None:
    toot_text = "なし"
  if toot_text0 == '' or toot_text0 == None:
    toot_text0 = "なし"

  toot_account_full_id = "@" + toots['account']['acct']
  if ("@" in toots['account']['acct']) == False:
    toot_account_full_id += "@" + url[8:] # URL https://xxxxxxxx の前提

  toot_account = ''
  toot_account0 = toot_account
  nSpeaker = -1  
  if len(replace_id2name) > 0:
    for element in replace_id2name['users']:
      id = element['id']
      if id == toot_account_full_id:
        nSpeaker = element['sp']
        toot_account = element['name']
        toot_account0 = toots['account']['display_name']
        if toot_account0 == '':
          toot_account0 = toots['account']['acct']
        if toot_account0 == '':
          toot_account0 = toots['account']['username']
        break

  MAX_SPEAKER_ID = useVV.getMaxSpeakerID()
  if MAX_SPEAKER_ID>= 0:
    if nSpeaker < 0 or nSpeaker > MAX_SPEAKER_ID:
      nSpeaker = toots['account']['id'] % MAX_SPEAKER_ID

  # ここまでで toot_account があれば喋る対象。''なら喋らない
  if toot_account != '':
    if toots['reblog'] != None:
      toot_account += "がブースト。"
      toot_text0 = "[ブーストされたToot]\n" + toot_text0
      if toots['reblog']['media_attachments'] != []:
        toot_text += "。メディアあり"
        toot_text0 += " メディアあり"
  else:
    if toots['reblog'] != None:
      toot_account += "ブースト。"
      toot_text0 = "[ブーストされたToot]\n" + toot_text0
      if toots['reblog']['media_attachments'] != []:
        toot_text += "。メディアあり"
        toot_text0 += " メディアあり"

  if toot_account != "":
    toot_text = toot_account + '　' + toot_text
  

  q2.put((nSpeaker, toots['account']['id'], toot_text, toot_account_full_id, toot_text0))
  
  result = {}
  result['toot_account0'] = toot_account0
  result['toot_account_full_id'] = toot_account_full_id
  result['toot_text0'] = toot_text0
  if toots['reblog'] != None:
    result['boosted_avatar'] = toots['reblog']['account']['avatar_static']
  else:
    result['boosted_avatar'] = ''
  return result

class MyListener(StreamListenerEx):
  def on_update(self, toot):
    global q1
    q1.put(toot)

  def on_notification(self, notification): #通知が来た時に呼び出されます
    global q1
    if notification['type'] == 'mention': #通知の内容がリプライかチェック
        q1.put(notification['status'])

def worker():
  global q2, lock 

  while True:
    if not q1.empty(): # 次のTootがある場合
      toot = q1.get()
      if toot.get('toot_account_full_id') != None:
        # 時報
        update_toot(toot, toot)
        q2.put((toot['speaker'],'', toot['toot_text0'], '', toot['toot_text0'].replace('\n', '')))
      else:
        # 通常Toot
        result = do_1toot(toot)
        update_toot(toot, result)

    if not q2.empty():
      (nSpeaker, account_id, toot_text, toot_account_full_id, toot_text0) = q2.get()
      if nSpeaker != '':
        if useVV.checkVV() == True:
          useVV.speak_toot(nSpeaker, account_id, toot_text, toot_account_full_id, toot_text0)
          sleep(0.3)


    sleep(0.1) # もう少し短くしてもいいだろうが、まぁいいや

def update_toot(toot, result):
  global ICON_W_H, g_data

  s = ""
  toot_account0 = result['toot_account0']
  toot_account_full_id = result['toot_account_full_id']
  toot_text0 = result['toot_text0']
  boosted_avatar = result['boosted_avatar']
  
  if toot_account0 != '':
      s = toot_account0 + '(' + toot_account_full_id + ')'
  else:
      s = toot_account_full_id
  name = s
  toot_text = toot_text0

  url = toot['account']['avatar_static']
  if url[0:7] == '[LOCAL]':
    img = cv2.imread(url[7:])
  else:
    img = imread_web(url)
  img = cv2.resize(img, dsize=(ICON_W_H, ICON_W_H), interpolation=cv2.INTER_AREA)
  img = cv_to_base64(img)
  img_avatar = img
    
  if boosted_avatar != '':
    url = boosted_avatar
    img = imread_web(url)
    img = cv2.resize(img, dsize=(24, 24), interpolation=cv2.INTER_AREA)
    img = cv_to_base64(img)
    img_boosted_avatar = img
  else:
    img_boosted_avatar = None
  
  lock.acquire()
  g_data.toot_id = toot['id']
  g_data.name = name
  g_data.toot_text = toot_text
  g_data.img_avatar = img_avatar
  g_data.img_boosted_avatar = img_boosted_avatar
  lock.release()

def put_toot(nSpeaker, now, toot):
  global png_files, q1
  t ={ "speaker":-1, "id":'', "toot_account0":'', "toot_account_full_id":'', "toot_text0":'', "account": { "avatar_static":'' }, "boosted_avatar":'' }
  t['speaker'] = nSpeaker
  t['id']= 'TIME' + now.strftime('%Y%m%d%H%M%S')
  t['toot_account0'] = ''
  t['toot_account_full_id'] = 'Clock'
  t['toot_text0'] = toot
  t['account']['avatar_static'] = '[LOCAL]' + png_files[random.randint(0, len(png_files)-1)]
  q1.put(t)


def main():
  global ICON_W_H, ICON_W_H_2, WAV_PLAYING, png_files, JST, FLAG_USE_LTL
  global mastodon, listener, useVV, lock, g_data, prev_toot_id

  mastodon = init()
  listener = MyListener()
  useVV = UseVV.UseVV()

  # HTL
  th1 = threading.Thread(target = mastodon.stream_user, args=([listener, False]))
  th1.setDaemon(True)
  th1.start()

  # LTL
  list = []
  if FLAG_USE_LTL == True:
    try:
      list = mastodon.timeline_local(limit=1)
    except:
      FLAG_USE_LTL = False
  if len(list) > 0:
      th = threading.Thread(target = mastodon.stream_local, args=([listener, False]))
      th.setDaemon(True)
      th.start()

  # FTL
  if FLAG_USE_FTL == True:
      th = threading.Thread(target = mastodon.stream_public, args=([listener, False]))
      th.setDaemon(True)
      th.start()

  sg.theme('DarkBrown1')
  path = pathlib.Path('user_set.txt')

  th2 = threading.Thread(target = worker)
  th2.setDaemon(True)
  th2.start()

  col1 = [
    [ sg.Text('(name)', text_color='yellow', font=(None, 14), key='-NAME-') ]
  ]
  col2 = [
    [
        sg.Text('(Toot)', text_color='white', font=(None, 14), size=(26, 5), key='-TOOT-'),
        sg.Image(data=None, size=(ICON_W_H_2, ICON_W_H_2), key='-BOOSTED_AVATAR-'),
        sg.Image(data=None, size=(ICON_W_H, ICON_W_H), key='-AVATAR-')
    ]
  ]
  col3 = [
    [ sg.Text('(time)', text_color='white', font=(None, 14), key='-TIME-', enable_events=True) ]
  ]

  layout = [
    [sg.Column(col1)],
    [sg.Column(col2)],
    [sg.Column(col3, justification='right')]
  ]

  # scaling=2.0にするとWindows 4Kででかすぎたw
  window = sg.Window('VoTLMasG', layout, size=(360, 160),
    auto_size_buttons=False, keep_on_top=True, grab_anywhere=True,  
    resizable=True, element_padding=(0, 0))

  limit_time = datetime.datetime.now(JST)
  unlock_counter = 0

  while True:
    event, _ = window.read(timeout=16) # msec
    if event == sg.WIN_CLOSED or event == 'Quit':
        break
    
    if event == '-TIME-':
      screen_width, screen_height = window.get_screen_dimensions()
      win_width, win_height = window.size
      x, y = (screen_width - win_width) - 2, (screen_height - win_height) - 2-28
      window.move(x, y)


    now = datetime.datetime.now(JST)
    h = now.hour; m = now.minute; s = now.second

    if FLAG_USE_CLOCK == True:
      if now >= limit_time:
        if (h == 22) and (m == 21) and (s == 40):
          if useVV.checkVV() == True:
            nSpeaker = random.randint(0, useVV.getMaxSpeakerID())
            s = 'に...'

            put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない
    
        if (h == 22) and (m == 21) and (s == 50):
          if useVV.checkVV() == True:
            nSpeaker = random.randint(0, useVV.getMaxSpeakerID())
            s = 'にゃ...'

            put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない
    
        if (h == 22) and (m == 22) and (s == 00):
          if useVV.checkVV() == True:
            nSpeaker = random.randint(0, useVV.getMaxSpeakerID())
            s = 'にゃんにゃんにゃんにゃんにゃんにゃんにゃんにゃん'

            put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない

        if (m % 5 == 0) and (s == 0):
          if useVV.checkVV() == True:
            nSpeaker = random.randint(0, useVV.getMaxSpeakerID())
            s = 'にゃーん。\n'
            s += useVV.getSpeakerNameFromSpeakerID(nSpeaker) + "が\n"
            s += '午前' + str(h) if h <= 12 else '午後' + str(h - 12)
            s += '時' + str(m) + '分くらいを\nお知らせします。'
            
            put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない

    
    dt = now.strftime('%Y/%m/%d(%a) %H:%M:%S')
    window['-TIME-'].update(dt)

    g_data_local = None    
    lock.acquire()
    toot_id = g_data.toot_id
    if toot_id != prev_toot_id:
      g_data_local = copy.deepcopy(g_data)
    lock.release()
    
    if toot_id != prev_toot_id:
      prev_toot_id = toot_id
      window['-NAME-'].update(g_data_local.name)
      window['-TOOT-'].update(g_data_local.toot_text)
      window['-AVATAR-'].update(data=g_data_local.img_avatar)
      window['-BOOSTED_AVATAR-'].update(data=g_data_local.img_boosted_avatar)
      
  window.close()

if __name__ == '__main__':
    main()