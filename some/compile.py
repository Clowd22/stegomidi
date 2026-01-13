from mido import MidiFile

# ドレミファソラシド (C4〜C5) に対応するMIDIノート番号と3ビット値
note_to_bits = {
    60: '000',  # C4
    62: '001',  # D4
    64: '010',  # E4
    65: '011',  # F4
    67: '100',  # G4
    69: '101',  # A4
    71: '110',  # B4
    72: '111'   # C5 (オクターブ上)
}

# MIDIファイルを読み込み
midi = MidiFile("test1001.mid")
bit_sequence = ""

# ノートオンイベントからビット列を復元
for track in midi.tracks:
    for msg in track:
        if msg.type == 'note_on' and msg.velocity > 0:
            if msg.note in note_to_bits:
                bit_sequence += note_to_bits[msg.note]

print(f"復元されたビット列:\n{bit_sequence}")

# bit_sequenceをUTF-8文字列に変換
bytes_list = []
for j in range(0, len(bit_sequence), 8):
    byte = bit_sequence[j:j+8]
    if len(byte) == 8:
        bytes_list.append(int(byte, 2))
if bytes_list:
    text = bytes(bytes_list).decode('utf-8', errors='ignore')
else:
    text = ""
print("▼ 復元された文字列:")
print(text)
