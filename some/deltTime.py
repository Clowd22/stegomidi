# check_delta_time.py

from mido import MidiFile

def check_midi_delta_time(midi_file_path):
    """
    指定されたMIDIファイルの各イベントのデルタタイムを表示します。
    """
    try:
        mid = MidiFile(midi_file_path)
        print(f"ファイル名: {midi_file_path}")
        print("-" * 30)

        for i, track in enumerate(mid.tracks):
            print(f"--- トラック {i} ---")
            total_time = 0
            for msg in track:
                # 各イベントのtimeパラメータがデルタタイム
                delta_time = msg.time
                total_time += delta_time
                print(f"デルタタイム: {delta_time:<5} | 総時間: {total_time:<5} | メッセージ: {msg}")
            print("-" * 30)

    except FileNotFoundError:
        print(f"エラー: ファイルが見つかりません - {midi_file_path}")

if __name__ == '__main__':
    file_name = input("確認したいMIDIファイル名を入力してください: ")
    check_midi_delta_time(file_name)
