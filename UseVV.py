from re import sub
import requests
import datetime
import random
import os
import subprocess

if os.name != 'nt':
    # macやUbuntuの場合
    from playsound import playsound
if os.name == 'nt':
    # Windowsの場合(playsoundだとマシだと言われている1.2.2でもWAVの書き換えができないっぽい)
    import winsound


class UseVV:
  def __init__(self):
    self.address_port = 'localhost:50021' # VOICEVOX
    self.MAX_SPEAKERS = -1
    self.vv_data = []
  
      # audioフォルダ
    if os.path.isdir('audio') == False:
      os.mkdir('audio')
      

  # VOICEVOX が起動しているか
  # VOICEVOXのSpeakersの最大数。0からなので数としては+1になる(14なら15種類)
  def checkVV(self):
    try:
      res = requests.get('http://' + self.address_port + '/speakers')
      self.vv_data = res.json()
      for dt in self.vv_data:
        for dt2 in dt['styles']:
          id = dt2['id']
          if self.MAX_SPEAKERS < id:
            self.MAX_SPEAKERS = id
    except:
      self.MAX_SPEAKERS = -1

    if self.MAX_SPEAKERS < 0:
      return False
    return True
  
  def playMySound(self, soundFile):
    if os.name == 'nt':
      with open(soundFile, 'rb') as f:
        data = f.read()
        winsound.PlaySound(data, winsound.SND_MEMORY)
    else:
      playsound(soundFile)

  def speak_toot(self, nSpeaker, account_id, toot_text, toot_account_full_id, toot_text0):
    print("WAV作成・再生: Start " + datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S'))
    
    try:
      f = open('audio/text.txt', 'w', encoding='UTF-8')
      f.write(toot_text)
      f.close()
      
      if nSpeaker < 0:
        nSpeaker = account_id % self.MAX_SPEAKERS
      
      s = 'curl -s -X POST "' + self.address_port + '/audio_query?speaker=' + str(nSpeaker) + '" --get --data-urlencode text@audio/text.txt > audio/query.json'
      subprocess.run(s, shell=True)

      # Windowsでは '' で囲うとwavが作成されなかった...
      s = "curl -s -H \"Content-Type: application/json\" -X POST -d @audio/query.json \"" + self.address_port + "/synthesis?speaker=" + str(nSpeaker) + "\" > \"audio/audio.wav\""
      subprocess.run(s, shell=True)

      if os.path.getsize("audio/audio.wav") < 100:
        print("[CreateFile Error !!] audio/audio.wav")
        return

      print(f"({nSpeaker}) : {toot_account_full_id} : {toot_text0}\r")
      self.playMySound("audio/audio.wav")
      print("WAV作成・再生: End")
      return True

    except:
      print("Error at speak_toot()")
      self.playMySound('audioError.wav')
      self.vv_data = []
      self.MAX_SPEAKERS = -1  
      return False
  
  def getMaxSpeakerID(self):
    return self.MAX_SPEAKERS
  
  def getSpeakerNameFromSpeakerID(self, nSpeakerID):
    if self.MAX_SPEAKERS < 0:
      return ''
    
    for d1 in self.vv_data:
      if len(d1['styles']) > 1:            
        for d2 in d1['styles']:
          if d2['id'] == nSpeakerID:
            return d1['name'] + "(" + d2['name'] + ")"
      else:
        if d1['styles'][0]['id'] == nSpeakerID:
          return d1['name']
    return ''
