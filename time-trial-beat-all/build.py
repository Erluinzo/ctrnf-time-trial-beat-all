#!/usr/bin/env python3
"""Builds package/patches/TimeTrialBeatAll.xml from src/beat_all.s.

  python3 build.py [path/to/eboot.elf]     (default: ../../CTRNF/out/eboot.elf)

The eboot is only read, to check the original bytes and to compute the ExpectedSHA256 values
the launcher checks before it applies the patch.
"""
import hashlib, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ELF = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / 'CTRNF/out/eboot.elf'
XML = HERE / 'package/patches/TimeTrialBeatAll.xml'
# The owner tests each build at once: a copy goes into the game's patches folder, switched on.
TEST_COPY = HERE.parent.parent / 'CTRNF/patches/TimeTrialBeatAll.xml'
EBOOT_BASE = 0x400000       # patch XML addresses are ELF addresses + 0x400000

HOOK = 0xfcc890             # the game's "unlock the next ghost" step, 23 bytes up to 0xfcc8a7
HOOK_END = 0xfcc8a7
HOOK_ORIGINAL = bytes.fromhex('488b55c0 8b4a0c 413b4d34 750a ffc1 894a0c 41c6453001')
CAVE = 0x2338000            # unused zero padding at the end of the code segment (0x2317810-0x233c078)


def read(elf, va, n):
    # The code segment starts at file offset 0x4000 with address 0.
    return elf[0x4000 + va:0x4000 + va + n]


def assemble():
    with tempfile.TemporaryDirectory() as tmp:
        obj, out, binary = (Path(tmp) / name for name in ('a.o', 'a.elf', 'a.bin'))
        subprocess.run(['as', '--64', '-o', obj, HERE / 'src/beat_all.s'], check=True)
        subprocess.run(['ld', '-Ttext=%#x' % CAVE, '-e', 'beat_all', '-o', out, obj], check=True)
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', out, binary], check=True)
        return binary.read_bytes()


def main():
    elf = ELF.read_bytes()
    if read(elf, HOOK, len(HOOK_ORIGINAL)) != HOOK_ORIGINAL:
        sys.exit(f'{ELF}: the code at {HOOK:#x} is not the expected USA 1.21 code')
    cave = assemble()
    if read(elf, CAVE, len(cave)) != bytes(len(cave)):
        sys.exit(f'{ELF}: the area at {CAVE:#x} is not empty')

    # call beat_all, then jump over the rest of the replaced bytes
    call = b'\xe8' + (CAVE - (HOOK + 5)).to_bytes(4, 'little', signed=True)
    jump = b'\xeb' + bytes([HOOK_END - (HOOK + 7)])
    hook = call + jump + b'\x90' * (HOOK_END - HOOK - 7)

    # Signature: the replaced code and the 3 bytes before it ("mov al, [rbp-0x49]")
    signature = read(elf, HOOK - 3, 3 + len(hook))
    if elf.count(signature) != 1:
        sys.exit('the hook signature is not unique')

    def line(va, value, sig=None):
        sha = hashlib.sha256(read(elf, va, len(value))).hexdigest()
        extra = f' Signature="{sig.hex(" ")}" SignatureOffset="0x3"' if sig else ''
        return (f'      <Line Type="bytes" Address="{va + EBOOT_BASE:#010x}" Value="{value.hex()}"'
                f'{extra} ExpectedSHA256="{sha}" />')

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- Built by build.py from src/beat_all.s: edit those, not this file.
     Line 1: at the end of a Time Trial, the ghost manager (ELF 0xfcc430) unlocks only the ghost
     after the one you raced. The hook replaces that step with a call to line 2.
     Line 2: new code in unused padding; it does the game's step, then keeps unlocking while the
     next ghost on the track is slower than your time. -->
<Patch>
  <TitleID><ID>CUSA13795</ID></TitleID>
  <Metadata Title="Crash Team Racing Nitro-Fueled" Name="Time Trial: Beat Every Ghost at Once"
            Note="One Time Trial run unlocks every ghost slower than your time, not only the next one."
            Author="Neox" PatchVer="0.1.0" AppVer="01.21" AppElf="eboot.bin">
    <PatchList>
{line(HOOK, hook, signature)}
{line(CAVE, cave)}
    </PatchList>
  </Metadata>
</Patch>
'''
    XML.write_text(xml, encoding='utf-8')
    print(f'{XML.relative_to(HERE)}: hook {len(hook)} bytes at {HOOK:#x}, code {len(cave)} bytes at {CAVE:#x}')
    if TEST_COPY.parent.is_dir():
        TEST_COPY.write_text(xml.replace('AppElf="eboot.bin">', 'AppElf="eboot.bin" isEnabled="true">'), encoding='utf-8')
        print(f'test copy, switched on: {TEST_COPY}')


if __name__ == '__main__':
    main()
