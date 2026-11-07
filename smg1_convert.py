#!/usr/bin/env python3
"""
EXPERIMENTAL Super Mario Galaxy 1 save converter: Wii <-> Switch (GameData.bin).

    python smg1_convert.py wii2switch  wii_GameData.bin    switch_GameData.bin
    python smg1_convert.py switch2wii  switch_GameData.bin wii_GameData.bin

Switch saves come in two layouts: "v1" (what game version 1.0.0 writes: the Wii layout,
little-endian) and "latest" (newer versions add extra fields). switch2wii reads both
automatically. For wii2switch, pick the output layout with --switch-format v1|latest
(default v1, which matches 1.0.0 saves).

NOT TESTED ON REAL HARDWARE. Back up your saves first, and test on a spare slot.
Format knowledge comes from the galaxy_save_data / galaxy_save_core Rust crates
plus byte-level comparison of real saves from both platforms.
"""
import struct, sys, datetime

# ---- constants taken from blank (new-game) saves of each platform ----
WII_FLG_KEYS = [31418, 3214, 6223, 3678, 25317, 22885, 19491, 6272, 15718, 11477, 20088, 8647, 30996, 31802, 3915, 20899, 31892, 27764, 1538, 14180, 5001, 14490, 32048, 20523, 5731, 6237, 134, 26369, 7764, 4183, 16143, 2807, 17962, 3450, 5818, 14449, 18841, 15582, 18392, 154, 5100, 18522, 17068, 22689, 31745, 381, 31792, 29618, 16707, 19084, 20900, 22973, 22371, 17040, 12972, 27109, 10978]
SW_FLG_KEYS = [23868, 22426, 22525, 23381, 2402, 1977, 8076, 30140, 18395, 16004, 17131, 8647, 30996, 31802, 3915, 20899, 31892, 27764, 1538, 14180, 5001, 14490, 32048, 20523, 5731, 6237, 134, 26369, 7764, 4183, 16143, 2807, 17962, 3450, 5818, 14449, 18841, 15582, 18392, 154, 5100, 18522, 17068, 22689, 31745, 381, 31792, 29618, 16707, 19084, 20900, 22973, 22371, 17040, 12972, 27109, 10978]
WII_VLE_KEYS = [20028, 20158, 36249, 36379, 15857, 15987, 6579, 6709, 54925, 55055, 36418, 39619, 1145, 48576, 31795, 31655, 29403, 46282, 10163, 25332, 40501, 55670, 5303, 20472]
SW_VLE_TEMPLATE = [(18194, 0), (18324, 5400), (46768, 65535), (46898, 65535), (21204, 0), (21334, 5400), (38306, 0), (38436, 5400), (51206, 0), (51336, 5400), (36418, 1), (8723, 0), (1145, 65280), (48576, 0), (31795, 0), (31655, 0), (29403, 0), (46282, 0), (33637, 449), (10163, 0), (25332, 0), (40501, 0), (55670, 0), (5303, 0), (20472, 0)]   # (key, default value); index 18 is Switch-only
SW_GALA_HDR = bytes.fromhex("2a0006003400088200009621020023d403007e810400a82d1400d18d2400")
WII_GALA_HDR = bytes.fromhex("002a000400148208000021960002d4230003817e0004")

SW_EXTRA_VLE_INDEX = 18          # VLE1 entry that exists only in the newer Switch layout
SWITCH_FORMAT = 'v1'             # output layout for wii2switch: 'v1' or 'latest'
OS_EPOCH = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
WII_TICKS_PER_SEC = 60750000     # Wii OSTime ticks/second
FLAG_ASSUMED = {6: 2, 7: 2}      # ASSUMPTION: Wii config flag -> Switch flag (cosmetic; see notes)

# ---------------- checksum / container ----------------
def checksum(buf, e):
    n = len(buf) // 2
    v = struct.unpack(e + '%dH' % n, buf[:n * 2])
    return ((sum(v) & 0xffff) << 16) | (sum((~x) & 0xffff for x in v) & 0xffff)

def read_container(d, e):
    h = struct.unpack(e + 'IIII', d[:16])
    if h[0] != checksum(d[4:], e): raise ValueError('container checksum mismatch (wrong platform/endianness?)')
    if h[3] != len(d): raise ValueError('file size field does not match file length')
    ents = []
    for i in range(h[2]):
        o = 16 + i * 16
        ents.append([d[o:o + 12].split(b'\0')[0].decode(), struct.unpack(e + 'I', d[o + 12:o + 16])[0]])
    for i, x in enumerate(ents):
        x.append(ents[i + 1][1] if i + 1 < len(ents) else len(d))
    return h, ents

def write_container(h, ents, blocks, e):
    out = bytearray(h[3])
    struct.pack_into(e + 'III', out, 4, h[1], h[2], h[3])
    for i, (nm, off, end) in enumerate(ents):
        out[16 + i * 16:16 + i * 16 + 12] = nm.encode().ljust(12, b'\0')
        struct.pack_into(e + 'I', out, 16 + i * 16 + 12, off)
        b = blocks[nm]; assert len(b) == end - off, nm
        out[off:end] = b
    struct.pack_into(e + 'I', out, 0, checksum(bytes(out[4:]), e))
    return bytes(out)

def decode_block(b, e):
    ver, n = b[0], b[1]; p = 4; chunks = []
    for _ in range(n):
        tag = b[p:p + 4]
        hs, sz = struct.unpack(e + 'II', b[p + 4:p + 12])
        if e == '<': tag = tag[::-1]
        chunks.append((tag.decode('ascii'), hs, b[p + 12:p + sz])); p += sz
    return ver, chunks

def encode_block(ver, chunks, e, size):
    out = bytearray([ver, len(chunks), 0, 0])
    for tag, hs, data in chunks:
        data = bytes(data)
        if e == '<':
            data += b'\0' * ((-(12 + len(data))) % 4)     # Switch chunks are 4-byte aligned
            out += tag.encode()[::-1]
        else:
            out += tag.encode()
        out += struct.pack(e + 'II', hs, 12 + len(data)) + data
    if len(out) > size: raise ValueError('converted block does not fit in its slot')
    return bytes(out) + b'\0' * (size - len(out))

U16 = lambda b, e: list(struct.unpack(e + '%dH' % (len(b) // 2), b[:len(b) // 2 * 2]))
P16 = lambda v, e: struct.pack(e + '%dH' % len(v), *v)

# ---------------- chunk converters ----------------
def play_w2s(d):
    story = d[0]; bits, lives = struct.unpack('>IH', d[1:7])
    if SWITCH_FORMAT == 'v1': return bytes([story]) + struct.pack('<IH', bits, lives)
    o = bytearray(32); o[0] = story
    struct.pack_into('<IH', o, 1, bits, lives)   # remaining Switch-only fields (boss flags etc.) left at 0
    return bytes(o)
def play_s2w(d):
    bits, lives = struct.unpack('<IH', d[1:7])
    return bytes([d[0]]) + struct.pack('>IH', bits, lives)

def swap16(d, a, b): return P16(U16(d, a), b)

def spn_swap(b, a, c):
    n = b[0]; out = bytearray([n]); p = 1
    for _ in range(n):
        name, dsz = struct.unpack(a + 'HH', b[p:p + 4]); sn = b[p + 4]; gs = p
        out += struct.pack(c + 'HH', name, dsz) + bytes([sn, b[p + 5]]); p += 6
        for _ in range(sn):
            ssz = struct.unpack(a + 'H', b[p:p + 2])[0]
            out += struct.pack(c + 'H', ssz) + b[p + 2:p + ssz]; p += ssz
        if p - gs != dsz: raise ValueError('SPN1 size mismatch')
    return bytes(out)

def gala_parse(d, e):
    n, cnt, esz = struct.unpack(e + 'HHH', d[:6]); base = 6 + 4 * cnt; g = []
    for i in range(n):
        o = base + i * esz
        name = struct.unpack(e + 'H', d[o:o + 2])[0]
        g.append(dict(name=name, ps=d[o + 2], fp=d[o + 3], coins=U16(d[o + 4:o + 20], e),
                      clear=U16(d[o + 20:o + 36], e) if esz >= 52 else None,
                      miss=U16(d[o + 36:o + 52], e) if esz >= 52 else None))
    return g
def gala_w2s(d):
    if SWITCH_FORMAT == 'v1':
        out = bytearray(P16(U16(WII_GALA_HDR, '>'), '<'))
        for x in gala_parse(d, '>'):
            out += struct.pack('<H', x['name']) + bytes([x['ps'], x['fp']]) + P16(x['coins'], '<')
        return bytes(out)
    out = bytearray(SW_GALA_HDR)
    for x in gala_parse(d, '>'):
        clear = [1 if (x['fp'] >> i) & 1 else 0 for i in range(8)]   # inferred rule, see notes
        out += struct.pack('<H', x['name']) + bytes([x['ps'], x['fp']]) + P16(x['coins'], '<') + P16(clear, '<') + P16([0] * 8, '<')
    return bytes(out)
def gala_s2w(d):
    out = bytearray(WII_GALA_HDR)
    for x in gala_parse(d, '<'):
        out += struct.pack('>H', x['name']) + bytes([x['ps'], x['fp']]) + P16(x['coins'], '>')
    return bytes(out)

def flg_w2s(d):
    v = U16(d, '>')[:len(WII_FLG_KEYS)]
    if [x & 0x7fff for x in v] != WII_FLG_KEYS: raise ValueError('unexpected FLG1 keys (different game version?)')
    return P16([k | (x & 0x8000) for k, x in zip(SW_FLG_KEYS, v)] + [0], '<')
def flg_s2w(d):
    v = U16(d, '<')[:len(SW_FLG_KEYS)]
    if [x & 0x7fff for x in v] != SW_FLG_KEYS: raise ValueError('unexpected FLG1 keys (different game version?)')
    return P16([k | (x & 0x8000) for k, x in zip(WII_FLG_KEYS, v)], '>')

def vle_w2s(d):
    v = U16(d, '>'); ent = list(zip(v[0::2], v[1::2]))
    if [k for k, _ in ent] != WII_VLE_KEYS: raise ValueError('unexpected VLE1 keys (different game version?)')
    out = []; wi = 0
    for j, (k, val) in enumerate(SW_VLE_TEMPLATE):
        if j == SW_EXTRA_VLE_INDEX:
            if SWITCH_FORMAT == 'latest': out.append((k, val))
            continue
        out.append((k, ent[wi][1])); wi += 1
    if SWITCH_FORMAT == 'latest' and (out[2][1], out[3][1]) == (0, 5400): out[2] = (out[2][0], 65535); out[3] = (out[3][0], 65535)   # default marker differs
    return P16([x for kv in out for x in kv], '<')
def vle_s2w(d):
    v = U16(d, '<'); ent = list(zip(v[0::2], v[1::2]))
    if len(ent) == len(SW_VLE_TEMPLATE) - 1: ent = [(k, val) for k, val in ent]; has_extra = False   # v1 layout
    elif len(ent) == len(SW_VLE_TEMPLATE): has_extra = True                                          # latest layout
    else: raise ValueError('unexpected VLE1 size (%d entries)' % len(ent))
    want = [k for j, (k, _) in enumerate(SW_VLE_TEMPLATE) if has_extra or j != SW_EXTRA_VLE_INDEX]
    if [k for k, _ in ent] != want: raise ValueError('unexpected VLE1 keys (different game version?)')
    vals = [val for j, (_, val) in enumerate(ent) if not (has_extra and j == SW_EXTRA_VLE_INDEX)]
    if has_extra and (vals[2], vals[3]) == (65535, 65535): vals[2], vals[3] = 0, 5400   # marker used only by the newer layout
    return P16([x for kv in zip(WII_VLE_KEYS, vals) for x in kv], '>')

def conf_w2s(d): return bytes([d[0], 0, 0, 0])
def conf_s2w(d): return bytes([d[0]])
def mii_w2s(d): return d[:8] + bytes([0, d[9], 0, 0])
def mii_s2w(d): return d[:8] + bytes([0, d[9]])
def misc_w2s(d):
    ticks = struct.unpack('>Q', d[1:9])[0]
    unix = int((OS_EPOCH + datetime.timedelta(seconds=ticks / WII_TICKS_PER_SEC)).timestamp()) if ticks else 0
    return bytes([FLAG_ASSUMED.get(d[0], 1)]) + struct.pack('<Q', unix) + bytes(3)   # assist-mode byte stays 0
def misc_s2w(d):
    unix = struct.unpack('<Q', d[1:9])[0]
    ticks = int((datetime.datetime.fromtimestamp(unix, datetime.timezone.utc) - OS_EPOCH).total_seconds() * WII_TICKS_PER_SEC) if unix else 0
    ticks = max(ticks, 0)
    return bytes([6 if d[0] >= 2 else 1]) + struct.pack('>Q', ticks)                  # assist mode is dropped
def sysc_w2s(d): return P16(U16(d[:16], '>'), '<') + bytes(len(d) - 16)
def sysc_s2w(d): return P16(U16(d[:16], '<'), '>') + bytes(len(d) - 16)

W2S = dict(PLAY=play_w2s, FLG1=flg_w2s, PCE1=lambda d: swap16(d, '>', '<'), SPN1=lambda d: spn_swap(d, '>', '<'),
           VLE1=vle_w2s, GALA=gala_w2s, CONF=conf_w2s, MISC=misc_w2s, SYSC=sysc_w2s); W2S['MII '] = mii_w2s
S2W = dict(PLAY=play_s2w, FLG1=flg_s2w, PCE1=lambda d: swap16(d, '<', '>'), SPN1=lambda d: spn_swap(d, '<', '>'),
           VLE1=vle_s2w, GALA=gala_s2w, CONF=conf_s2w, MISC=misc_s2w, SYSC=sysc_s2w); S2W['MII '] = mii_s2w

def convert(data, direction):
    src, dst, table = ('>', '<', W2S) if direction == 'wii2switch' else ('<', '>', S2W)
    h, ents = read_container(data, src)
    blocks = {}
    for nm, off, end in ents:
        ver, chunks = decode_block(data[off:end], src)
        new = [(t, hs, table[t](dat)) for t, hs, dat in chunks]
        blocks[nm] = encode_block(ver, new, dst, end - off)
    return write_container(h, ents, blocks, dst)

if __name__ == '__main__':
    args = sys.argv[1:]
    if '--switch-format' in args:
        i = args.index('--switch-format')
        if i + 1 >= len(args) or args[i + 1] not in ('v1', 'latest'): sys.exit(__doc__)
        SWITCH_FORMAT = args[i + 1]; del args[i:i + 2]
    if len(args) != 3 or args[0] not in ('wii2switch', 'switch2wii'):
        sys.exit(__doc__)
    out = convert(open(args[1], 'rb').read(), args[0])
    open(args[2], 'wb').write(out)
    print('wrote', args[2], len(out), 'bytes' + (' (Switch layout: %s)' % SWITCH_FORMAT if args[0] == 'wii2switch' else ''))
