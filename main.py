if __name__ == '__main__':
  print("しばらくお待ちください。\n全ての「初期化完了」が終わっても何もウィンドウが表示されない場合はCtrl-Cで終了して再度実行してください。")

import base64
from io import BytesIO
from pkgutil import get_data
import random, tempfile
from urllib.parse import uses_relative
from cv2 import imread
from pytz import timezone
import requests, pathlib, time
import datetime
from lib2to3.pytree import convert
import re, os, json
from time import sleep
import threading, queue, glob, copy
from dateutil import tz
import html

from PIL import Image, ImageTk
import cv2, PySimpleGUI as sg, demoji

from mastodonEx import MastodonEx, StreamListenerEx
import UseVV

      
class TootManager:
  MAX_TOOT_LETTERS = 255 # 何文字までしゃべるか。あまり長いとVOICEVOXが落ちるかもしれないので注意

  class GL_data:
    toot_id = -1
    name = ''
    toot_text = ''
    img_avatar = None
    img_boosted_avatar = None

  class MyListener(StreamListenerEx):
    def __init__(self, server_address):
      self.server_address = server_address
    
    # 例外ってどこで拾うんだ？とりあえずこうやってみよう
    def on_update(self, toot):
      toot['server'] = self.server_address
      TootManager.queue.put(toot)

    def on_notification(self, notification): #通知が来た時に呼び出されます
      if notification['type'] == 'mention': #通知の内容がリプライかチェック
        notification['status']['server'] = self.server_address
        TootManager.queue.put(notification['status'])

    def on_error(self, status_code):
      str = 'ERROR:エラーが発生しました。 Error Code: ' + str(status_code)
      print(str)
      sg.popup(str)
      
      
  # class変数
  instance_number = 0
  queue = queue.Queue() # Toot表示用
  lock = threading.Lock()
  useVV = UseVV.UseVV()
  tooted_id = {}
  tooted_str = {}
  toot_account = {}
  share_data = GL_data()
  ICON_W_H = 100 # アイコンサイズ
  ICON_W_H_2 = 32 # BTアイコンのサイズ
  png_files = ''
  png_folder = ''
  replace_content = {}
  replace_id2name = {}
  # GETで得られるデータで本文(content)には <p></p>がだいたいついているので消すための準備
  conv = re.compile(r"<[^>]*?>")
  # URLは喋らせると長いので丸ごと消すための準備
  convURL = re.compile(r"(https?|ftp)(:\/\/[-_\.!~*\'()a-zA-Z0-9;\/?:\@&=\+\$,%#]+)")


  def imread_web(self, url):
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
  
  def pil_to_base64(self, img, format="png"):
      buffer = BytesIO()
      img.save(buffer, format)
      img_str = base64.b64encode(buffer.getvalue()).decode("ascii")
      return img_str

  def cv_to_base64(self, img):
      _, encoded = cv2.imencode(".png", img)
      img_str = base64.b64encode(encoded).decode("ascii")
      return img_str

  def remove_emoji(self, src_str):
    return demoji.replace(string=src_str, repl="")
  
  def worker(self):
    q2 = queue.Queue()

    while True:
      if not TootManager.queue.empty(): # 次のTootがある場合
        toot = TootManager.queue.get()
        
        # 時報の場合は無条件に表示更新＋喋る
        if toot.get('toot_account_full_id') != None:
          # 時報
          self.update_toot(toot, toot)
          print("\nDbg: 時報: " + toot['toot_text0'].replace('\n', ''))
          q2.put((toot['speaker'],'', toot['toot_text0'], '', toot['toot_text0'].replace('\n', '')))      
          if not q2.empty():
            (nSpeaker, account_id, toot_text, toot_account_full_id, toot_text0) = q2.get()
            if TootManager.useVV.checkVV() == True:
              TootManager.useVV.speak_toot(nSpeaker, account_id, toot_text, toot_account_full_id, toot_text0)
          sleep(2.0)
        
        # 通常Tootの場合
        else:
          # まず、ログインIDを割り出す。というのも、同じサーバーであれば @xxxx@xxxxxxx@xxx ではなく xxx になってしまうので
          s = toot['account']['acct']
          a_id = toot['account']['id']
          if s[0] != "@":
            s = "@" + s
          if s[1:].find('@') < 0:
            s = s + '@' + toot['server'][8:]
            
          # 同一サーバーのLTL/HTLで、同じTootは2回目以降は除外　Toot IDで判別
          bFlagProc = True
          print("\nServer: " + toot['server'])
          if TootManager.tooted_id.get(toot['id']) == None:
            # 今回が初検出の場合
            print("(0A)Dbg: tooted_id.get(toot['id']) == None ... このTootは初検出(同一サーバー内)")
            if len(TootManager.tooted_id) > 1000:
              print("  (0B)Dbg: tooted_id == {}")
              TootManager.tooted_id = {}
            TootManager.tooted_id[toot['id']] = 1
          else:
            # すでにToot済みの場合
            print("(0C)Dbg: tooted_id.get(toot['id']) == None: " + str(TootManager.tooted_id[toot['id']]) + ", len(TootManager.tooted_id)=" + str(len(TootManager.tooted_id)) + " ... このTootはToot済み(同一サーバー内)")
            bFlagProc = False # この場合、もう処理する必要がない（表示も発声も）
          
          # 初Tootの場合 or 別サーバーでの重複Tootの場合、の二択か
          if bFlagProc != False:
            # しゃべる対象の人か？(喋らなくても表示は更新するので、ここで終わりでは無い)
            bSpeakFlag = True
            if TootManager.toot_account.get(s) == None:
              bSpeakFlag = False
            
            if self.FLAG_SPEAK_ALL_ACCOUNT == True:
              bSpeakFlag = True

            # すでに同じセリフをしゃべっていないか
            # URL関連や改行関連など、サーバーごとに微妙に異なることがあるのでこれで完璧！ではない
            s = toot['content']
            s = html.unescape(s) # 例えば I&apos;m を I'm に戻す 
            print("  (1:" +  str(a_id) + ")Dbg: Str(Org):  " + s)
            s = s.replace('\n', '')
            s = s.replace('<br />', '')
            s = s.replace('<br>', '')
            s = TootManager.conv.sub("", s) # <x>xxxxx</x>  を全て抽出

            # ここまでの段階では "RT @"がないので無意味だった
            # "RT @xxxx 本文" の場合、"本文" までカットする (複数RT先指定がある場合には無意味だが多くは単一指定だろう...)
            idx = s.find('RT @')
            if idx >= 0:
              s0 = s[idx+4:]
              s = s[0:idx] + s0[s0.find(' ')+1:]
            
            print("  (2:" +  str(a_id) + ")Dbg: Str(調整): " + s)
            if TootManager.tooted_str.get(s) == None:
              print("    (3A)Dbg: tooted_str.get(s) == None, len(TootManager.tooted_str)=" + str(len(TootManager.tooted_str)))
              if len(TootManager.tooted_str) > 32:
                print("      (4)Dbg: tooted_str == {}")
                TootManager.tooted_str = {}
              TootManager.tooted_str[s] = 1
            else:
              print("    (3B)Dbg: tooted_str.get(s) != None: " + str(TootManager.tooted_str[s]) + ", len(TootManager.tooted_str)=" + str(len(TootManager.tooted_str)))
              bFlagProc = False

            if bFlagProc == True:
              if bSpeakFlag == True:             
                print("  (9A) bFlagProc == True, 表示更新＋スピーク")
              else:
                print("  (9B) bFlagProc == True, 表示更新のみ")

              #ここに来たら、表示更新していない・しゃべっていない ---> 今から更新する・しゃべる
              result = self.do_1toot(q2, toot)
              self.update_toot(toot, result)  # 表示更新

              if not q2.empty():
                (nSpeaker, account_id, toot_text, toot_account_full_id, toot_text0) = q2.get()
                if nSpeaker != '':
                  if bSpeakFlag == True and TootManager.useVV.checkVV() == True:
                    TootManager.useVV.speak_toot(nSpeaker, account_id, html.unescape(toot_text), toot_account_full_id, html.unescape(toot_text0))
                    sleep(0.3)
                  else:
                    sleep(2.0) # 喋らない時は待ち時間を伸ばす
              
            else:
              print("(9B) bFlagProc == False, ↑ 表示更新・スピーク　省略")
              # del TootManager.tooted_str[s]
            
      sleep(0.1)

  def __init__(self, account_info, flags):
    print("初期化開始")
    
    self.appname = 'VoTLMasG'

    self.FLAG_TOOT_SPOILER_TEXT = flags['FLAG_TOOT_SPOILER_TEXT']
    self.FLAG_USE_LTL = flags['FLAG_USE_LTL']
    self.FLAG_USE_FTL = flags['FLAG_USE_FTL']
    self.FLAG_SPEAK_ALL_ACCOUNT = flags['FLAG_SPEAK_ALL_ACCOUNT']

    cid_file = 'file_cid_' + account_info + '.txt'
    token_file = 'file_access_token_' + account_info + '.txt'
    FILE_SETTINGS_1 = 'init_mysettings.json'
    FILE_SETTINGS_2 = 'init_mysettings3.json'

    # ログイン情報
    try:
      json_open = open(FILE_SETTINGS_1, 'r', encoding='UTF-8')
    except:
      s = f"ERROR: {FILE_SETTINGS_1} が準備できていません。READMEを確認ください。"
      print(s)
      sg.popup(s)
      exit()

    try:  
      json_load = json.load(json_open)
      url = json_load[account_info]['url']
      if url[0:8] != "https://":
        s = "ERROR: https:// からアドレスが始まるWebサイトのみ対応です。" # これ以降で先頭8文字が"https://"前提のところがあるので
        print(s)
        sg.popup(s)
        exit()
      print(f"　server({TootManager.instance_number}) = " + url)
      email = json_load[account_info]['user_id']
      password = json_load[account_info]['password']
      
      if TootManager.png_folder == '':
        TootManager.png_folder= json_load[account_info]['png_folder']
        if TootManager.png_folder[-1] == '/' or TootManager.png_folder[-1] == '\\':
          TootManager.png_folder = TootManager.png_folder[0:len(TootManager.png_folder)-1] 
        TootManager.png_files = glob.glob(TootManager.png_folder + "/*.png")
            
    except:
      s = f"ERROR: {FILE_SETTINGS_1} の内容が適切ではありません。READMEを確認ください。"
      print(s)
      sg.popup(s)
      exit()
    
    # 文字列置換情報
    if len(TootManager.replace_content) == 0:
      json_open = None
      try:
        json_open = open(FILE_SETTINGS_2, 'r', encoding='UTF-8')
      except:
        s = "{FILE_SETTINGS_2} が存在しないため名前をしゃべりません。また、単語変換もないため不自然な発声が多くなります。\nREADMEを確認し、{FILE_SETTINGS_2}を設定されることをお勧めします。"
        print(s)
        sg.popup(s)

      if json_open != None:
        try:
          json_load = json.load(json_open)
          TootManager.replace_id2name = json_load['replace_id2name']
          TootManager.replace_content = json_load['replace_content']
          
          for i in TootManager.replace_id2name['users']:
            TootManager.toot_account[i['id']] = 1
        except:
          s = f"ERROR: {FILE_SETTINGS_2} の内容が適切ではありません。READMEを確認ください。"
          print(s)
          sg.popup(s)
          exit()


    try:
      if os.path.isfile(cid_file) == False:
        MastodonEx.create_app(self.appname, api_base_url = url, to_file = cid_file )
        mastodon = MastodonEx( client_id = cid_file, api_base_url = url, )
        mastodon.log_in( username = email, password = password, to_file = token_file )
      else:
        mastodon = MastodonEx( client_id=cid_file, access_token=token_file, api_base_url=url )
    except:
      s = f"ERROR: {FILE_SETTINGS_1} の内容が適切ではありません。READMEを確認ください。"
      print(s)
      sg.popup(s)
      exit()
    self.server_address = url

    # self.convp = re.compile('[a-zA-Z0-9!\"“#$%\&\'’()=\-~|¥\]+`@\{\}*;:<>?,./_。 \n\u200B]+')
    print("初期化完了\n")
    self.mastodon = mastodon
    self.listener = TootManager.MyListener(self.server_address)

    # HTL
    th = threading.Thread(target = self.mastodon.stream_user, args=([self.listener, False]))
    th.setDaemon(True)
    th.start()

    # LTL
    if self.FLAG_USE_LTL == True:
      list = []
      try:
        list = mastodon.timeline_local(limit=1)
        if len(list) > 0:
          th = threading.Thread(target = self.mastodon.stream_local, args=([self.listener, False]))
          th.setDaemon(True)
          th.start()
      except:
        pass

    # FTL
    if self.FLAG_USE_FTL == True:
        th = threading.Thread(target = self.mastodon.stream_public, args=([self.listener, False]))
        th.setDaemon(True)
        th.start()
        th = threading.Thread(target = self.mastodon.stream_public, args=([self.listener, False]))
        th.setDaemon(True)
        th.start()
    
    if TootManager.instance_number == 0:
      th = threading.Thread(target = self.worker)
      th.setDaemon(True)
      th.start()
    TootManager.instance_number += 1

  def put_toot(self, nSpeaker, now, toot):
    t ={ "speaker":-1, "id":'', "toot_account0":'', "toot_account_full_id":'', "toot_text0":'', "account": { "avatar_static":'' }, "boosted_avatar":'' }
    t['speaker'] = nSpeaker
    t['id']= 'TIME' + now.strftime('%Y%m%d%H%M%S')
    t['toot_account0'] = ''
    t['toot_account_full_id'] = 'Clock'
    t['toot_text0'] = toot
    t['server'] = self.server_address
    
    if len(TootManager.png_files) > 0:
      t['account']['avatar_static'] = '[LOCAL]' + TootManager.png_files[random.randint(0, len(TootManager.png_files)-1)]
    else:
      t['account']['avatar_static'] = None
    TootManager.queue.put(t)

  def update_toot(self, toot, result):
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
      img = self.imread_web(url)
    img = cv2.resize(img, dsize=(TootManager.ICON_W_H, TootManager.ICON_W_H), interpolation=cv2.INTER_AREA)
    img = self.cv_to_base64(img)
    img_avatar = img
      
    if boosted_avatar != '':
      url = boosted_avatar
      img = self.imread_web(url)
      img = cv2.resize(img, dsize=(TootManager.ICON_W_H_2, TootManager.ICON_W_H_2), interpolation=cv2.INTER_AREA)
      img = self.cv_to_base64(img)
      img_boosted_avatar = img
    else:
      img_boosted_avatar = None
    
    TootManager.lock.acquire()
    TootManager.share_data.toot_id = toot['id']
    TootManager.share_data.name = name
    TootManager.share_data.toot_text = toot_text
    TootManager.share_data.img_avatar = img_avatar
    TootManager.share_data.img_boosted_avatar = img_boosted_avatar
    TootManager.lock.release()

  def do_1toot(self, q2, toots):
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
      toot_text = html.unescape(toot_text)

      if toots['spoiler_text'] != '':
        toot_text = toots['spoiler_text'] + " 。[たたむ]。 " + toot_text if self.FLAG_TOOT_SPOILER_TEXT == True else ""

      toot_text = toot_text.replace('\n', '。')
      toot_text = toot_text.replace('<br />', '。')
      toot_text = toot_text.replace('<br>', '。')
      toot_text = TootManager.conv.sub("", toot_text) # <x>xxxxx</x>  を全て抽出

      toot_text0 = toot_text
      
      # emoji除去
      toot_text = self.remove_emoji(toot_text)

      # 単純に <a href以降を削除すると、リプがダメになる！
      # @u32 てすと　は、
      # '<p><span class="h-card"><a href="https://fedibird.com/@u32" class="u-url mention">@<span>u32</span></a></span> てすと</p>'
      # '<'と'>'の一式(中身を含む)を片っ端から削除する

      if toot_text.find('http') >= 0: # URLは長いのでしゃべりは省略
        toot_text = TootManager.convURL.sub("", toot_text)
        toot_text += "。URLあり"

      toot_text = toot_text.lower()

      for txt in TootManager.replace_content:
        if txt in toot_text:
          toot_text = toot_text.replace(txt, TootManager.replace_content[txt])

      
      if toots['media_attachments'] != []:
        toot_text += "。メディアあり"
        toot_text0 += " メディアあり"

      if len(toot_text) > TootManager.MAX_TOOT_LETTERS:
        toot_text = toot_text[:TootManager.MAX_TOOT_LETTERS] + "。以下略"
        toot_text0 = toot_text0[:TootManager.MAX_TOOT_LETTERS] + "。以下略"
        
      if toot_text == '' or toot_text == None:
        toot_text = "なし"
      if toot_text0 == '' or toot_text0 == None:
        toot_text0 = "なし"

      toot_account_full_id = "@" + toots['account']['acct']
      if ("@" in toots['account']['acct']) == False:
        toot_account_full_id += "@" + domain # URL https://xxxxxxxx の前提

      toot_account = ''
      toot_account0 = toot_account
      nSpeaker = -1  
      if len(TootManager.replace_id2name) > 0:
        for element in TootManager.replace_id2name['users']:
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

      MAX_SPEAKER_ID = TootManager.useVV.getMaxSpeakerID()
      if MAX_SPEAKER_ID>= 0:
        if nSpeaker < 0 or nSpeaker > MAX_SPEAKER_ID:
          nSpeaker = toots['account']['id'] % (MAX_SPEAKER_ID + 1)

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
      
      print("Stream(" + toots['server'] + "), account:" + toot_account_full_id + ", toot-id: " + str(toots['id']))
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


def main():
  # フラグ (HTLと通知は強制)
  flags = {
    'FLAG_USE_LTL': True, # ローカルTL (fedibirdのようにLTLがない場合は無意味)
    'FLAG_USE_FTL': False, # 連合TL (大量に流れるので片っ端からdomain_blockしてからでないと実用的ではないと思う)
    'FLAG_TOOT_SPOILER_TEXT': True, # CW (たたむ) の内容を喋るか
    'FLAG_SPEAK_ALL_ACCOUNT': False, # 全員喋るか
  }
  FLAG_USE_CLOCK = True, # 時報を喋るか
  CLOCK_INTERVAL_MINUTES = 15 # 何分ごとに時報を喋るか

  account_info1 = 'server_nickname_1'
  account_info2 = 'server_nickname_2'
  mastodon1 = TootManager(account_info1, flags)
  mastodon2 = TootManager(account_info2, flags)


  JST = tz.gettz('Asia/Tokyo')
  weekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] # 月曜から
  prev_toot_id = -1


  sg.theme('DarkBrown1')
  col1 = [
    [ sg.Text('(name)', text_color='yellow', font=(None, 14), key='-NAME-') ]
  ]
  col2 = [
    [
        sg.Text('(Toot)', text_color='white', font=(None, 14), size=(26, 5), key='-TOOT-'),
        sg.Image(data=None, size=(TootManager.ICON_W_H_2, TootManager.ICON_W_H_2), key='-BOOSTED_AVATAR-'),
        sg.Image(data=None, size=(TootManager.ICON_W_H, TootManager.ICON_W_H), key='-AVATAR-')
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
          if TootManager.useVV.checkVV() == True:
            nSpeaker = random.randint(0, TootManager.useVV.getMaxSpeakerID())
            s = 'に...'
            mastodon1.put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない
    
        if (h == 22) and (m == 21) and (s == 50):
          if TootManager.useVV.checkVV() == True:
            nSpeaker = random.randint(0, TootManager.useVV.getMaxSpeakerID())
            s = 'にゃ...'
            mastodon1.put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない
    
        if (h == 22) and (m == 22) and (s == 00):
          if TootManager.useVV.checkVV() == True:
            nSpeaker = random.randint(0, TootManager.useVV.getMaxSpeakerID())
            s = 'にゃんにゃんにゃんにゃんにゃんにゃんにゃんにゃん'
            mastodon1.put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない

        if (m % CLOCK_INTERVAL_MINUTES == 0) and (s == 0):
          if TootManager.useVV.checkVV() == True:
            nSpeaker = random.randint(0, TootManager.useVV.getMaxSpeakerID())
            s = 'にゃーん。\n'
            s += TootManager.useVV.getSpeakerNameFromSpeakerID(nSpeaker) + "が\n"
            s += '午前' + str(h) if h <= 12 else '午後' + str(h - 12)
            s += '時' + str(m) + '分くらいを\nお知らせします。'
            mastodon1.put_toot(nSpeaker, now, s)
            limit_time = now + datetime.timedelta(seconds=2) # 2秒後までは無視とすることで繰り返し実行をさせない

    dt = now.strftime('%Y/%m/%d(%a) %H:%M:%S')
    window['-TIME-'].update(dt)

    data_local = None    
    TootManager.lock.acquire()
    toot_id = TootManager.share_data.toot_id
    if toot_id != prev_toot_id:
      data_local = copy.deepcopy(TootManager.share_data)
    TootManager.lock.release()
    
    if toot_id != prev_toot_id:
      prev_toot_id = toot_id
      window['-NAME-'].update(data_local.name)
      window['-TOOT-'].update(data_local.toot_text)
      window['-AVATAR-'].update(data=data_local.img_avatar)
      window['-BOOSTED_AVATAR-'].update(data=data_local.img_boosted_avatar)


  window.close()

if __name__ == '__main__':
  main()
