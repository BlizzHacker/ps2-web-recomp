#!/usr/bin/env python3
"""Carve code regions from a RAM dump so eerecomp --overlay stays small.

Kingdom Hearts decompresses its executable into EE RAM at boot. The explore
loop stalls on "missing code at 0xADDR"; that address is inside a decompressed
region that is not in the on-disc ELF. This carves every nonzero code-bearing
region of the RAM dump around each miss address (and the known decompression
target) into separate raw overlays, so eerecomp only analyses real code and
not 32 MB of zeros.
"""
import sys, os

ram_path = sys.argv[1]
out_dir = sys.argv[2]
args = sys.argv[3:]
excludes = []   # list of (start, end) to skip — e.g. the ELF's own load range
positional = []
i = 0
while i < len(args):
    a = args[i]
    if a == '--exclude' and i + 1 < len(args):
        s, _, e = args[i + 1].partition(':')
        excludes.append((int(s, 16), int(e, 16)))
        i += 2
        continue
    positional.append(a)
    i += 1

miss_path = positional[0] if positional else None
seed_addrs = [int(a, 16) for a in positional[1:]]

RAM_SIZE = 32 << 20
data = open(ram_path, 'rb').read()
os.makedirs(out_dir, exist_ok=True)

# Collect the addresses we must cover
targets = set(seed_addrs)
if miss_path and os.path.exists(miss_path):
    for tok in open(miss_path).read().split():
        at = tok.split(':')[-1]
        try:
            a = int(at, 16)
        except ValueError:
            continue
        if a < 0x10000:   # kernel vector space — never user code
            continue
        targets.add(a)

def excluded(addr):
    return any(s <= addr < e for s, e in excludes)

def nonzero_span(addr):
    """Expand around addr to the enclosing run of nonzero 4-byte words,
    bounded so we don't swallow unrelated data. Returns (start, end)."""
    word = lambda o: data[o:o+4] != b'\x00\x00\x00\x00'
    if addr + 4 > len(data):
        return None
    start = addr
    # walk back up to 2MB
    back = 0
    while start >= 4 and back < (2 << 20) and word(start - 4):
        start -= 4
        back += 4
    end = addr + 4
    fwd = 0
    gap = 0
    while end < len(data) and fwd < (4 << 20):
        if word(end):
            gap = 0
        else:
            gap += 4
            if gap > 4 << 10:   # 4 KiB of zeros ends the region — keep overlays
                end -= gap      # tight; analyse() treats every word in a
                break           # segment as a code candidate, so padding junk
        end += 4                # poisons the translation
        fwd += 4
    return (start & ~3, end & ~3)

regions = []
for addr in sorted(targets):
    if excluded(addr):
        continue
    span = nonzero_span(addr)
    if not span:
        continue
    s, e = span
    # clip against excludes so we never re-translate the ELF's own pages
    for xs, xe in excludes:
        if s < xe and e > xs:
            if xs - s >= e - xe:
                e = xs
            else:
                s = xe
    if s >= e or excluded(s):
        continue
    # merge into existing overlapping region
    merged = False
    for i, (rs, re_) in enumerate(regions):
        if s <= re_ and e >= rs:
            regions[i] = (min(rs, s), max(re_, e))
            merged = True
            break
    if not merged:
        regions.append((s, e))

# de-overlap again after merges
regions.sort()
final = []
for s, e in regions:
    if final and s <= final[-1][1]:
        final[-1] = (final[-1][0], max(final[-1][1], e))
    else:
        final.append((s, e))

manifest = []
for i, (s, e) in enumerate(final):
    path = os.path.join(out_dir, 'overlay-%08x.bin' % s)
    open(path, 'wb').write(data[s:e])
    manifest.append((s, e, path))
    print('overlay 0x%08X..0x%08X (%d KiB) -> %s' % (s, e, (e - s) // 1024, path))

# emit the --overlay args for eerecomp
with open(os.path.join(out_dir, 'overlay-args.txt'), 'w') as f:
    for s, e, path in manifest:
        f.write('--overlay 0x%08X:%s\n' % (s, path))
print('total regions:', len(final))
