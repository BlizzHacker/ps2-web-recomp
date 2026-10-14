# Porting games that decompress themselves (RAM overlays)

Most PS2 titles run the executable that sits on the disc, and
`scripts/port.sh` handles them end to end. A few — Kingdom Hearts among
them — **decompress their real engine into EE RAM at boot and jump there**.
Static analysis of the on-disc ELF can never see that code, so the exploring
runs stall:

```
[ee] halted: missing code at 0x00F20000 (ra 0x001200D8)
```

and re-running `port.sh` makes no progress, because the miss address is not
in the ELF and adding it to `entries.txt` has nothing to translate.

Two small additions close the loop:

1. **`PS2_DUMP_RAM=<path>`** (native runner): when the EE halts, the runner
   writes the full 32 MiB EE RAM image to `<path>`. The decompressed code is
   sitting in that dump.
2. **`eerecomp --overlay <addr>:<file>`** (repeatable): adds a raw executable
   segment at a physical EE address, so the recovered region is analysed and
   translated together with the ELF. `analyse()` traces flow through
   `Image::word()`, so only real code inside the overlay is translated — the
   surrounding zeros and data are ignored.

## Recipe

```sh
GAME=games/kh; ELF=$GAME/disc/SLUS_203.70

# 1. run until it halts, dumping RAM
PS2_DUMP_RAM=/tmp/ram.bin build/native-kh/ps2run "$ELF" \
    --disc "$GAME/disc.iso" --frames 3600 --press 300:start \
    --misses $GAME/misses.txt

# 2. carve the code regions around every miss address, excluding the ELF's
#    own load range (readelf -l gives it) so nothing is translated twice
python3 scripts/carve_overlay.py /tmp/ram.bin $GAME/overlays \
    $GAME/all-misses.txt --exclude 00100000:0066CE98 00F20000

# 3. add the miss addresses as entry points, retranslate
cat $GAME/misses.txt >> $GAME/entries.txt   # normalise to hex first
build/tools/eerecomp "$ELF" --entries $GAME/entries.txt \
    $(tr '\n' ' ' < $GAME/overlays/overlay-args.txt) --out generated/kh

# 4. rebuild + rerun. The game boots further, hits the *next* decompressed
#    region, halts again — repeat from 1 until a run reaches the frame limit.
ninja -C build/native-kh ps2run
```

`scripts/carve_overlay.py` does step 2: it expands each miss address to the
enclosing run of nonzero words (64 KiB of zeros ends a region), clips out the
ELF's own pages, merges overlaps and writes one `overlay-XXXXXXXX.bin` per
region plus an `overlay-args.txt` with the `--overlay` flags ready to paste
into `eerecomp`.

On Kingdom Hearts (USA) this took the boot from frame 21 (first
`0x00F20000` halt) through the Square logo and title screen to steady
gameplay exploration within three rounds; the first round's overlay was just
26 KiB, growing to ~457 KiB as later decompression stages appeared.

## Why not a JIT fallback

The whole point of the static recompilation is that the EE is never
interpreted — that is what makes the frame rate. A runtime JIT would
reintroduce the interpreter the project exists to avoid, and cannot be
shipped in a page anyway without `eval`-class permissions COEP blocks. RAM
overlays keep the translation ahead of time and only ask the porter to run
the exploring loop until the game stops revealing new code.
