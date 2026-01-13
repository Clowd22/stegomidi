from mido import Message, MidiFile, MidiTrack
import math

# --- 定義 ---

# 音階対応（C4=60） - メロディのピッチに使用
pitch_table = {
    '000': 60,  # ド (C4)
    '001': 62,  # レ (D4)
    '010': 64,  # ミ (E4)
    '011': 65,  # ファ (F4)
    '100': 67,  # ソ (G4)
    '101': 69,  # ラ (A4)
    '110': 71,  # シ (B4)
    '111': 72   # ド↑ (C5)
}

# コード対応 - コードの種類と構成音の相対オフセット
# ルート音はchord_root_midi_note_mapで別途決定
chord_table = {
    '000': {'name': 'C', 'notes_offset': [0, 4, 7]},   # C Major (C, E, G)
    '001': {'name': 'Dm', 'notes_offset': [0, 3, 7]},  # D Minor (D, F, A)
    '010': {'name': 'Em', 'notes_offset': [0, 3, 7]},  # E Minor (E, G, B)
    '011': {'name': 'F', 'notes_offset': [0, 4, 7]},   # F Major (F, A, C)
    '100': {'name': 'G', 'notes_offset': [0, 4, 7]},   # G Major (G, B, D)
    '101': {'name': 'Am', 'notes_offset': [0, 3, 7]},  # A Minor (A, C, E)
    '110': {'name': 'Bdim', 'notes_offset': [0, 3, 6]}, # B Diminished (B, D, F)
    '111': {'name': 'CM7', 'notes_offset': [0, 4, 7, 11]} # C Major 7th (C, E, G, B)
}

# コードビット列に対応するルート音のMIDIノート (デコード時にchord_bitsを復元するために使用)
# '000'と'111'が衝突しないように、CM7のルート音をC5(72)に設定
chord_root_midi_note_map = {
    '000': 60, # C (C4)
    '001': 62, # Dm (D4)
    '010': 64, # Em (E4)
    '011': 65, # F (F4)
    '100': 67, # G (G4)
    '101': 69, # Am (A4)
    '110': 71, # Bdim (B4)
    '111': 72  # CM7 (C5) - 他と衝突しないようにC5に設定
}


# --- 入力データとバイナリ変換 ---
text = "Hello World"
binary_data = ''.join(f'{ord(c):08b}' for c in text)

# 8bitずつに区切る (3bit:pitch, 2bit:velocity_suffix, 3bit:chord_type)
chunk_size = 8
chunks = [binary_data[i:i+chunk_size].ljust(chunk_size, '0') for i in range(0, len(binary_data), chunk_size)]

# --- MIDIファイル作成 ---
mid = MidiFile()

# メロディトラック
melody_track = MidiTrack()
mid.tracks.append(melody_track)
# チャンネル設定 (例: メロディはチャンネル0)
melody_track.append(Message('program_change', channel=0, program=0, time=0)) # Grand Piano

# コードトラック
chord_track = MidiTrack()
mid.tracks.append(chord_track)
# チャンネル設定 (例: コードはチャンネル1)
chord_track.append(Message('program_change', channel=1, program=0, time=0)) # Grand Piano

# ベースベロシティ
base_velocity = 80  # 1010000

# 時間管理
# 各チャンク（音符と和音のセット）がどれくらいの長さで鳴るか
note_duration = 480  # ticks (4分音符=480 ticksと仮定, mid.ticks_per_beat=480がデフォルト)

# 各トラックの最初のイベントのtimeは0
# その後のイベントは `note_duration` のデルタタイムを持つようにすることで、
# 各チャンクの音符が順番に再生されるようにする。
# 最初のイベントのみ time=0, それ以降は time=note_duration とする。

first_event = True

for chunk in chunks:
    # チャンクから各情報を抽出
    pitch_bits = chunk[0:3]       # メロディの音階 (3bit)
    velocity_suffix_bits = chunk[3:5] # メロディのベロシティ下位2bit (2bit)
    chord_bits = chunk[5:8]       # コードの種類 (3bit)

    # 現在のデルタタイムを決定
    delta_time = 0
    if not first_event:
        delta_time = note_duration
    first_event = False

    # --- メロディの生成 ---
    melody_note = pitch_table[pitch_bits]

    # ベロシティの下位2bitを差し替え
    velocity_bin_prefix = format(base_velocity, '07b')[:5] # 上位5bitを維持
    new_melody_velocity = int(velocity_bin_prefix + velocity_suffix_bits, 2)

    # メロディのノートオン・オフイベントを追加
    melody_track.append(Message('note_on', note=melody_note, velocity=new_melody_velocity, time=delta_time))
    melody_track.append(Message('note_off', note=melody_note, velocity=0, time=note_duration)) # note_onからnote_duration後にオフ

    # --- コードの生成 ---
    chord_info = chord_table[chord_bits]
    chord_root_midi_note = chord_root_midi_note_map[chord_bits] # コードビットからルート音を決定

    # コードの構成音を追加
    # コードのベロシティはメロディとは独立して固定値とする
    chord_velocity = 64

    # 最初のコードノートオンのみdelta_timeを設定。残りの構成音はtime=0で同時鳴動
    for i, offset in enumerate(chord_info['notes_offset']):
        chord_note = chord_root_midi_note + offset
        if i == 0: # 最初の構成音
            chord_track.append(Message('note_on', note=chord_note, velocity=chord_velocity, time=delta_time))
        else: # それ以降の構成音は同時に鳴る (delta_time=0)
            chord_track.append(Message('note_on', note=chord_note, velocity=chord_velocity, time=0))

    # コードのノートオフイベント (全ての構成音を同時にオフ)
    # 最初の構成音のオフのみ note_duration 後、残りは time=0
    for i, offset in enumerate(chord_info['notes_offset']):
        chord_note = chord_root_midi_note + offset
        if i == 0: # 最初の構成音
            chord_track.append(Message('note_off', note=chord_note, velocity=0, time=note_duration))
        else: # それ以降の構成音は同時にオフ
            chord_track.append(Message('note_off', note=chord_note, velocity=0, time=0))


# --- 保存 ---
mid.save("hello_world_stego_multitrack.mid")
