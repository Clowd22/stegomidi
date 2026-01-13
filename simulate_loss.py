import argparse
import copy
import os
import random
import sys
from mido import MidiFile, MidiTrack, Message, MetaMessage

def collect_note_on_index(mid):
    """全トラックを走査し、(track_idx, msg_idx, note) のリストを返す（note_on velocity>0）"""
    lst = []
    for ti, track in enumerate(mid.tracks):
        for mi, msg in enumerate(track):
            if getattr(msg, "type", None) == "note_on" and getattr(msg, "velocity", 0) > 0:
                lst.append((ti, mi, msg.note))
    return lst

def find_matching_note_off(track, start_idx, note_num):
    """同トラック内で start_idx の次にある同じノートの note_off (または note_on vel=0) の index を返す（なければ None）"""
    for j in range(start_idx + 1, len(track)):
        m = track[j]
        if getattr(m, "type", None) == "note_off" and getattr(m, "note", None) == note_num:
            return j
        if getattr(m, "type", None) == "note_on" and getattr(m, "velocity", 0) == 0 and getattr(m, "note", None) == note_num:
            return j
    return None

def rebuild_track_from_kept(track, keep_mask):
    """keep_mask: bool list same length as track. 返り値: new MidiTrack (時間差を再計算)"""
    # build abs times of kept messages
    abs_list = []
    abs_t = 0
    for i, msg in enumerate(track):
        abs_t += getattr(msg, "time", 0)
        if keep_mask[i]:
            abs_list.append({"msg": copy.copy(msg), "abs": abs_t})
    # rebuild track
    new_track = MidiTrack()
    prev = 0
    for e in abs_list:
        m = e["msg"]
        delta = int(e["abs"] - prev)
        m.time = delta
        new_track.append(m)
        prev = e["abs"]
    return new_track

def remove_notes(mid, to_remove_set):
    """to_remove_set: set of (track_idx, msg_idx) pairs to delete. Returns new MidiFile."""
    new_mid = MidiFile()
    new_mid.ticks_per_beat = mid.ticks_per_beat
    for ti, track in enumerate(mid.tracks):
        keep_mask = [True] * len(track)
        for mi in range(len(track)):
            if (ti, mi) in to_remove_set:
                keep_mask[mi] = False
        new_track = rebuild_track_from_kept(track, keep_mask)
        new_mid.tracks.append(new_track)
    return new_mid

def build_removal_set(mid, note_on_list, mode, param):
    """note_on_list: list of (ti, mi, note). returns set of (ti, mi) and matching note_off indices to remove"""
    to_remove = set()
    if mode == "indices":
        # param: list of indices referring to note_on_list positions
        for idx in param:
            if idx < 0 or idx >= len(note_on_list):
                continue
            ti, mi, note = note_on_list[idx]
            to_remove.add((ti, mi))
            off_idx = find_matching_note_off(mid.tracks[ti], mi, note)
            if off_idx is not None:
                to_remove.add((ti, off_idx))
    elif mode == "every_n":
        n = int(param)
        for idx, (ti, mi, note) in enumerate(note_on_list):
            if (idx + 1) % n == 0:
                to_remove.add((ti, mi))
                off_idx = find_matching_note_off(mid.tracks[ti], mi, note)
                if off_idx is not None:
                    to_remove.add((ti, off_idx))
    elif mode == "random":
        pct = float(param)
        total = len(note_on_list)
        remove_count = int(round(total * pct / 100.0))
        indices = list(range(total))
        random.shuffle(indices)
        for idx in indices[:remove_count]:
            ti, mi, note = note_on_list[idx]
            to_remove.add((ti, mi))
            off_idx = find_matching_note_off(mid.tracks[ti], mi, note)
            if off_idx is not None:
                to_remove.add((ti, off_idx))
    return to_remove

def main():
    parser = argparse.ArgumentParser(description="simulate MIDI note loss for testing decode")
    parser.add_argument("input", nargs="?", help="input midi filename (in mid/)")
    parser.add_argument("--mode", choices=["indices", "every_n", "random"], default="random")
    parser.add_argument("--param", help="indices: comma separated note indices (0-based); every_n: integer N; random: percent (0-100)", required=False)
    parser.add_argument("--out", help="output filename (will be written to mid/)", required=False)
    args = parser.parse_args()

    # 対話モード: 引数 input が与えられていなければプロンプトする
    if not args.input:
        args.input = input("入力 MIDI ファイル名を mid/ から指定してください（例 Hello.mid）: ").strip()
        if args.input == "":
            print("入力が指定されませんでした。終了します。")
            return

    inpath = os.path.join("mid", args.input)
    if not os.path.exists(inpath):
        print("入力ファイルが見つかりません:", inpath)
        return

    mid = MidiFile(inpath)
    note_on_list = collect_note_on_index(mid)
    print(f"検出された note_on 数: {len(note_on_list)}")
    for i, (ti, mi, note) in enumerate(note_on_list):
        print(f"{i:3d}: track={ti} msg_idx={mi} note={note}")

    if args.mode == "indices":
        if not args.param:
            print("indices モードを使う場合 --param にカンマ区切りの index を与えてください")
            return
        ids = [int(x.strip()) for x in args.param.split(",") if x.strip() != ""]
        param = ids
    elif args.mode == "every_n":
        if not args.param:
            print("every_n モードを使う場合 --param に N を与えてください")
            return
        param = int(args.param)
    else:
        param = float(args.param) if args.param else 10.0  # デフォルト 10%

    to_remove_set = build_removal_set(mid, note_on_list, args.mode, param)
    print(f"削除予定のメッセージ数 (note_on と note_off を含む): {len(to_remove_set)}")
    print(sorted(list(to_remove_set))[:20], "...")
    new_mid = remove_notes(mid, to_remove_set)

    outname = args.out if args.out else args.input.replace(".mid", "") + "_corrupt.mid"
    outpath = os.path.join("mid", outname)
    new_mid.save(outpath)
    print("破損ファイルを出力しました:", outpath)

if __name__ == "__main__":
    main()
