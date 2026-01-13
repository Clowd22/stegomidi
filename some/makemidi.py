from mido import Message, MidiFile, MidiTrack
import math

# 音階対応（C4=60）
pitch_table = {
    '000': 60,  # ド
    '001': 62,  # レ
    '010': 64,  # ミ
    '011': 65,  # ファ
    '100': 67,  # ソ
    '101': 69,  # ラ
    '110': 71,  # シ
    '111': 72   # ド↑
}

# 入力文字列とバイナリ変換
text = input("Enter text to encode in MIDI: ")
title = input("Enter title for the MIDI file: ")
binary_data = ''.join(f'{ord(c):08b}' for c in text)
chunks = [binary_data[i:i+5].ljust(5, '0') for i in range(0, len(binary_data), 5)]

# MIDIファイル作成
mid = MidiFile()
track = MidiTrack()
mid.tracks.append(track)

base_velocity = 80  # 1010000

time = 0
for chunk in chunks:
    pitch_bits = chunk[:3]
    velocity_bits = chunk[3:]

    note = pitch_table[pitch_bits]

    # ベロシティの下位2bitを差し替え
    velocity_bin = format(base_velocity, '07b')
    new_velocity_bin = velocity_bin[:5] + velocity_bits
    new_velocity = int(new_velocity_bin, 2)

    # ノートオン・オフ
    track.append(Message('note_on', note=note, velocity=new_velocity, time=time))
    track.append(Message('note_off', note=note, velocity=0, time=240))  # 240 ticks later

# 保存
mid.save(f"{title}.mid")
