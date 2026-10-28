#!/usr/bin/env python3
"""Runs the built patch code (from package/patches/TimeTrialBeatAll.xml) in a CPU emulator,
with fake game objects, and checks which ghosts it unlocks.

  python3 test_beat_all.py      (needs: pip install unicorn)
"""
import re, struct, unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RBX, UC_X86_REG_R12, UC_X86_REG_R13, \
    UC_X86_REG_RBP, UC_X86_REG_RSP

XML = (Path(__file__).resolve().parent / 'package/patches/TimeTrialBeatAll.xml').read_text()
LINES = {int(a, 16) - 0x400000: bytes.fromhex(v) for a, v in re.findall(r'Address="(0x[0-9a-f]+)" Value="([0-9a-f]+)"', XML)}
CAVE = 0x2338000
FIND_LEVEL_GHOSTS = 0xf9b970
DATA, STACK, RETURN = 0x10000000, 0x20000000, 0x30000000
# Ghost times on a made-up track, in the game's order: N. Tropy, Oxide, Velo, Developer (seconds)
TIMES = [270.0, 220.0, 180.0, 168.0]


def run(index, raced, my_time, times=TIMES, have_level=True):
    """Index of the track record after the race, the _unlockedNewGhost flag, and checks."""
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    for base in (CAVE & ~0xfff, FIND_LEVEL_GHOSTS & ~0xfff, DATA, STACK, RETURN):
        uc.mem_map(base, 0x10000)
    uc.mem_write(CAVE, LINES[CAVE])

    manager, record, entry, ghost_list, items, ghosts = (DATA + 0x100 * i for i in range(6))
    uc.mem_write(manager + 0x30, b'\0')
    uc.mem_write(manager + 0x34, struct.pack('<i', raced))
    uc.mem_write(record + 0xc, struct.pack('<i', index))
    uc.mem_write(entry + 0x20, struct.pack('<Q', ghost_list))
    uc.mem_write(ghost_list + 0xc, struct.pack('<i', len(times)))
    uc.mem_write(ghost_list + 0x20, struct.pack('<Q', items))
    for i, t in enumerate(times):
        ghost = ghosts + 0x40 * i
        uc.mem_write(items + 8 * i, struct.pack('<Q', ghost))
        uc.mem_write(ghost + 0x20, struct.pack('<f', t))
    # find_level_ghosts: "mov rax, entry (or 0); ret"
    uc.mem_write(FIND_LEVEL_GHOSTS, b'\x48\xb8' + struct.pack('<Q', entry if have_level else 0) + b'\xc3')

    rbp = STACK + 0x8000
    uc.mem_write(rbp - 0x40, struct.pack('<Q', record))
    uc.mem_write(rbp - 0x70, struct.pack('<f', my_time))
    uc.mem_write(rbp - 0x80, struct.pack('<Q', DATA + 0x800))
    rsp = rbp - 0x100                       # 16-byte aligned, as in the caller's body
    rsp -= 8
    uc.mem_write(rsp, struct.pack('<Q', RETURN))
    for reg, value in ((UC_X86_REG_RBP, rbp), (UC_X86_REG_RSP, rsp), (UC_X86_REG_R13, manager),
                       (UC_X86_REG_RAX, 0x1111111111111101), (UC_X86_REG_RBX, 0x2222), (UC_X86_REG_R12, 0x3333)):
        uc.reg_write(reg, value)

    misaligned = []
    def on_call(uc, address, size, _):
        if (uc.reg_read(UC_X86_REG_RSP) + 8) % 16:
            misaligned.append(address)
    uc.hook_add(UC_HOOK_CODE, on_call, begin=FIND_LEVEL_GHOSTS, end=FIND_LEVEL_GHOSTS)
    uc.emu_start(CAVE, RETURN)

    assert not misaligned, 'stack not 16-byte aligned at the call'
    assert uc.reg_read(UC_X86_REG_RSP) == rsp + 8, 'stack not balanced'
    assert uc.reg_read(UC_X86_REG_RAX) == 0x1111111111111101, 'rax (al) not kept'
    assert (uc.reg_read(UC_X86_REG_RBX), uc.reg_read(UC_X86_REG_R12)) == (0x2222, 0x3333), 'rbx/r12 not kept'
    new_index, = struct.unpack('<i', uc.mem_read(record + 0xc, 4))
    return new_index, uc.mem_read(manager + 0x30, 1)[0]


class BeatAll(unittest.TestCase):
    def test_owner_example(self):
        # Race N. Tropy at 173 s: Tropy, Oxide and Velo are beaten, Developer (168 s) can be raced.
        self.assertEqual(run(index=0, raced=0, my_time=173.0), (3, 1))

    def test_faster_than_all(self):
        self.assertEqual(run(index=0, raced=0, my_time=150.0), (4, 1))

    def test_only_the_raced_ghost(self):
        # Slower than Oxide: the game's own step only.
        self.assertEqual(run(index=0, raced=0, my_time=230.0), (1, 1))

    def test_no_ghost_yet(self):
        # First run beats the track's unlock time and also Tropy's time.
        self.assertEqual(run(index=-1, raced=-1, my_time=250.0), (1, 1))

    def test_no_ghost_yet_slow(self):
        # Beats only the unlock time: Tropy can now be raced.
        self.assertEqual(run(index=-1, raced=-1, my_time=290.0), (0, 1))

    def test_raced_an_older_ghost(self):
        # Velo can be raced (index 2) but you raced Tropy; you were also faster than Velo.
        self.assertEqual(run(index=2, raced=0, my_time=175.0), (3, 1))

    def test_nothing_new(self):
        self.assertEqual(run(index=2, raced=0, my_time=200.0), (2, 0))

    def test_all_beaten(self):
        self.assertEqual(run(index=4, raced=3, my_time=100.0), (4, 0))

    def test_level_not_found(self):
        # No ghost list for this level: the game's own step only.
        self.assertEqual(run(index=0, raced=0, my_time=100.0, have_level=False), (1, 1))

    def test_nan_time(self):
        self.assertEqual(run(index=1, raced=1, my_time=100.0, times=[270.0, 220.0, float('nan'), 168.0]), (2, 1))


if __name__ == '__main__':
    unittest.main()
