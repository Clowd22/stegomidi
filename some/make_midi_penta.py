# makemidi_7bit.py

from mido import Message, MidiFile, MidiTrack
import math

# --- 埋め込みルールと対応表 ---

# ヨナ抜き音階対応 (C5付近)
pitch_table = {
    '000': 72,  # ド↑ (C5)
    '001': 74,  # レ↑ (D5)
    '010': 76,  # ミ↑ (E5)
    '011': 79,  # ソ↑ (G5)
    '100': 81,  # ラ↑ (A5)
    '101': 84,  # ド↑↑ (C6)
    '110': 86,  # レ↑↑ (D6)
    '111': 88   # ミ↑↑ (E6)
}

# 時間対応 (2ビット) - ノート自体の長さ（duration）を決定
duration_table = {
    '00': 480,   # 4分音符
    '01': 960,   # 2分音符
    '10': 240,   # 8分音符
    '11': 1920   # 全音符
}

# --- 入力文字列とバイナリ変換 ---
text = input("Enter text to encode in MIDI: ")
title = input("Enter title for MIDI data:  ")
binary_data = ''.join(f'{ord(c):08b}' for c in text)

# 7bitチャンクに分割 (3bit:ピッチ, 2bit:長さ, 2bit:ベロシティ)
chunks = [binary_data[i:i+7].ljust(7, '0') for i in range(0, len(binary_data), 7)]

# --- MIDIファイル作成 ---
mid = MidiFile()
track = MidiTrack()
mid.tracks.append(track)

base_velocity = 80 # 基準ベロシティ (1010000)
delta_time = 0     # ノートが連続するため、常に0


for chunk in chunks:
    # チャンクから各情報を抽出
    pitch_bits = chunk[:3]         # 3ビット: 音階
    duration_bits = chunk[3:5]     # 2ビット: 長さ
    velocity_bits = chunk[5:7]     # 2ビット: ベロシティ下位ビット
    
    # 音楽要素の決定
    note = pitch_table[pitch_bits]
    note_duration = duration_table[duration_bits]
    
    # ベロシティの下位2bitを差し替え
    velocity_bin = format(base_velocity, '07b')
    new_velocity_bin = velocity_bin[:5] + velocity_bits
    new_velocity = int(new_velocity_bin, 2)
    
    # ノートオン・オフ
    track.append(Message('note_on', note=note, velocity=new_velocity, time=delta_time))
    
    # note_offのtimeに、音符の長さを設定
    track.append(Message('note_off', note=note, velocity=0, time=note_duration))
    
# --- 保存 ---
output_filename = f"{title}.mid"
mid.save(output_filename)
print(f"\nMIDIファイル '{output_filename}' が作成されました。")
