# -*- coding: utf-8 -*-

BIT_TO_NOTE = {
    '000': 'ド',
    '001': 'レ',
    '010': 'ミ',
    '011': 'ファ',
    '100': 'ソ',
    '101': 'ラ',
    '110': 'シ',
    '111': 'ド↑'
}

NOTE_TO_BIT = {v: k for k, v in BIT_TO_NOTE.items()}

def text_to_binary_padded(text):
    # 字列 → 各文字のUnicode値 → 8bitのバイナリ文字列
    binary = ''.join(format(ord(c), '08b') for c in text)
    
    # 余りには0を加える
    while len(binary) % 3 != 0:
        binary += '0'
        
    print(binary)
    return binary

def binary_to_notes(binary):
    return [BIT_TO_NOTE[binary[i:i+3]] for i in range(0, len(binary), 3)]

def text_to_notes(text):
    binary = text_to_binary_padded(text)
    notes = binary_to_notes(binary)
    return notes

def notes_to_binary(notes):
    return ''.join(NOTE_TO_BIT[note] for note in notes)

def binary_to_text(binary):
    # パディング分を除去（8bit単位に切り詰め）
    cut = len(binary) % 8
    if cut != 0:
        binary = binary[:-cut]
    # 8bitごとにバイトに変換
    byte_arr = bytearray(int(binary[i:i+8], 2) for i in range(0, len(binary), 8))
    # UTF-8デコードして文字列に戻す
    return byte_arr.decode('utf-8')

def notes_to_text(notes):
    # 音階 → 3bitのビット列に変換
    binary = ''.join(NOTE_TO_BIT[note] for note in notes)

    # パディング分を除去（8bit単位に切り詰め）
    cut = len(binary) % 8
    if cut != 0:
        binary = binary[:-cut]

    # 8bitごとに分割し文字に変換
    byte_arr = bytearray(int(binary[i:i+8], 2) for i in range(0, len(binary), 8))
    
    # UTF-8で文字列にデコード
    return byte_arr.decode('utf-8')

if __name__ == '__main__':
    message = input("🔤 テキストを入力してください: ")
    notes = text_to_notes(message)
    print("\n🎵 変換された音階:")
    print(notes)

    restored_text = notes_to_text(notes)
    print("\n🔁 復元されたテキスト:")
    print(restored_text)
