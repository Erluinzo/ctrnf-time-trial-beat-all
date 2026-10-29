#!/usr/bin/env python3
"""Builds the patch from src/beat_all.s, one mod package per game edition (the launcher needs each
package's XML to target one edition, and cannot pick between two ZIPs of one mod id):
  package/patches/TimeTrialBeatAll.xml           USA CUSA13795 1.21
  package-eu/patches/TimeTrialBeatAll-EU.xml     EU CUSA14876 1.21, with mod.json and README.txt made from package/
  python3 build.py

Each edition's executable is only read, to check the original bytes and to compute the
ExpectedSHA256 values the launcher checks before it applies the patch. The EU addresses were found
with ../tools/eu_map.py (same functions, moved by 0 to -0x40).
"""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME_DIR = HERE.parent.parent / 'CTRNF'
VERSION = '1.1.0'
EBOOT_BASE = 0x400000       # patch XML addresses are ELF addresses + 0x400000
HOOK_ORIGINAL = bytes.fromhex('488b55c0 8b4a0c 413b4d34 750a ffc1 894a0c 41c6453001')
CAVE = 0x2338000            # unused zero padding at the end of the code segment (USA 0x2317810-0x233c078,
                            # EU 0x23177d0-0x233c038)
# hook: the game's "unlock the next ghost" step, 23 bytes (HOOK_ORIGINAL) up to hook_end.
# game: what the code calls or reads (RIP-relative, so the linker must know the addresses).
# The owner tests each build at once: a copy goes into the game's patches folder, switched on.
EDITIONS = {
    'CUSA13795': dict(
        name='USA', elf=GAME_DIR / 'out/eboot.elf', xml=HERE / 'package/patches/TimeTrialBeatAll.xml',
        test_copy=GAME_DIR / 'patches/TimeTrialBeatAll.xml', hook=0xfcc890, hook_end=0xfcc8a7, manager=0xfcc430,
        game={'find_level_ghosts': 0xf9b970, 'add_stat': 0xaa2310, 'g_players': 0x2ad1160, 'g_stats': 0x2aa48c0,
              'beat_ntropy_ghost': 0x1cdb1d7, 'beat_oxide_ghost': 0x1cdb1e9, 'beat_velo_ghost': 0x1cdb1fa,
              'beat_dev_ghost': 0x1cdb20a}),
    'CUSA14876': dict(
        name='EU', elf=GAME_DIR / 'orig/CUSA14876-eboot.elf', xml=HERE / 'package-eu/patches/TimeTrialBeatAll-EU.xml',
        test_copy=GAME_DIR / 'patches/TimeTrialBeatAll-EU.xml', hook=0xfcc880, hook_end=0xfcc897, manager=0xfcc420,
        game={'find_level_ghosts': 0xf9b960, 'add_stat': 0xaa2310, 'g_players': 0x2ad1160, 'g_stats': 0x2aa48c0,
              'beat_ntropy_ghost': 0x1cdb197, 'beat_oxide_ghost': 0x1cdb1a9, 'beat_velo_ghost': 0x1cdb1ba,
              'beat_dev_ghost': 0x1cdb1ca}),
}


def read(elf, va, n):
    # The code segment starts at file offset 0x4000 with address 0.
    return elf[0x4000 + va:0x4000 + va + n]


def assemble(game):
    with tempfile.TemporaryDirectory() as tmp:
        obj, out, binary = (Path(tmp) / name for name in ('a.o', 'a.elf', 'a.bin'))
        subprocess.run(['as', '--64', '-o', obj, HERE / 'src/beat_all.s'], check=True)
        subprocess.run(['ld', '-Ttext=%#x' % CAVE, '-e', 'beat_all', '-o', out, obj,
                        *[f'--defsym={name}={address:#x}' for name, address in game.items()]], check=True)
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', out, binary], check=True)
        return binary.read_bytes()


def build(title, e):
    elf = e['elf'].read_bytes()
    hook_at, hook_end = e['hook'], e['hook_end']
    if read(elf, hook_at, len(HOOK_ORIGINAL)) != HOOK_ORIGINAL:
        sys.exit(f'{e["elf"]}: the code at {hook_at:#x} is not the expected {e["name"]} 1.21 code')
    for name, va in e['game'].items():     # the stat names must be the game's strings at those places
        if name.startswith('beat_') and read(elf, va, len(name) + 1) != name.encode() + b'\0':
            sys.exit(f'{e["elf"]}: "{name}" is not at {va:#x}')
    cave = assemble(e['game'])
    if read(elf, CAVE, len(cave)) != bytes(len(cave)):
        sys.exit(f'{e["elf"]}: the area at {CAVE:#x} is not empty')

    # call beat_all, then jump over the rest of the replaced bytes
    call = b'\xe8' + (CAVE - (hook_at + 5)).to_bytes(4, 'little', signed=True)
    jump = b'\xeb' + bytes([hook_end - (hook_at + 7)])
    hook = call + jump + b'\x90' * (hook_end - hook_at - 7)

    # Signature: the replaced code and the 3 bytes before it ("mov al, [rbp-0x49]")
    signature = read(elf, hook_at - 3, 3 + len(hook))
    if elf.count(signature) != 1:
        sys.exit('the hook signature is not unique')

    def line(va, value, sig=None):
        sha = hashlib.sha256(read(elf, va, len(value))).hexdigest()
        extra = f' Signature="{sig.hex(" ")}" SignatureOffset="0x3"' if sig else ''
        return (f'      <Line Type="bytes" Address="{va + EBOOT_BASE:#010x}" Value="{value.hex()}"'
                f'{extra} ExpectedSHA256="{sha}" />')

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- Built by build.py from src/beat_all.s: edit those, not this file.{" EU edition." if e["name"] == "EU" else ""}
     Line 1: at the end of a Time Trial, the ghost manager (ELF {e["manager"]:#x}) unlocks only the ghost
     after the one you raced. The hook replaces that step with a call to line 2.
     Line 2: new code in unused padding; it does the game's step, then keeps unlocking while the
     next ghost on the track is slower than your time. -->
<Patch>
  <TitleID><ID>{title}</ID></TitleID>
  <Metadata Title="Crash Team Racing Nitro-Fueled" Name="Time Trial: Beat Every Ghost at Once"
            Note="One Time Trial run unlocks every ghost slower than your time, not only the next one."
            Author="Onur" PatchVer="{VERSION}" AppVer="01.21" AppElf="eboot.bin">
    <PatchList>
{line(hook_at, hook, signature)}
{line(CAVE, cave)}
    </PatchList>
  </Metadata>
</Patch>
'''
    e['xml'].parent.mkdir(parents=True, exist_ok=True)
    e['xml'].write_text(xml, encoding='utf-8')
    print(f'{e["xml"].relative_to(HERE)}: hook {len(hook)} bytes at {hook_at:#x}, code {len(cave)} bytes at {CAVE:#x}')
    if e['test_copy'].parent.is_dir():
        e['test_copy'].write_text(xml.replace('AppElf="eboot.bin">', 'AppElf="eboot.bin" isEnabled="true">'),
                                  encoding='utf-8')
        print(f'test copy, switched on: {e["test_copy"]}')


def eu_package():
    """package-eu/ gets the USA package's README and manifest, with its own id and name"""
    manifest = json.loads((HERE / 'package/mod.json').read_text())
    assert manifest['version'] == VERSION, 'package/mod.json has another version'
    manifest.update(id=manifest['id'] + '-eu', name=manifest['name'] + ' (EU)',
                    patches=['patches/TimeTrialBeatAll-EU.xml'], files=[])
    (HERE / 'package-eu/mod.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy(HERE / 'package/README.txt', HERE / 'package-eu/README.txt')


def main():
    for title, e in EDITIONS.items():
        build(title, e)
    eu_package()


if __name__ == '__main__':
    main()
