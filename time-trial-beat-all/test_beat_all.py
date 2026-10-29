#!/usr/bin/env python3
"""Runs the built patch code (from package/patches/TimeTrialBeatAll.xml) in a CPU emulator,
with fake game objects shaped like the real ones, and checks which ghosts it unlocks.

  python3 test_beat_all.py      (needs: pip install unicorn; EU=1 tests the EU edition)

The real ghost table test reads looseData/GhostData.igz from the game in ../../CTRNF
(skipped when it is not there).
"""
import os, re, struct, sys, unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RBX, UC_X86_REG_R12, UC_X86_REG_R13, \
    UC_X86_REG_RBP, UC_X86_REG_RSP, UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX, UC_X86_REG_RCX, \
    UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_R14, UC_X86_REG_R15

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / 'CTRNF'
# EU=1 tests the EU edition's XML with its addresses (build.py EDITIONS)
sys.path.insert(0, str(HERE))
from build import EDITIONS
EDITION = EDITIONS['CUSA14876' if os.environ.get('EU') == '1' else 'CUSA13795']
XML = EDITION['xml'].read_text()
LINES = {int(a, 16) - 0x400000: bytes.fromhex(v) for a, v in re.findall(r'Address="(0x[0-9a-f]+)" Value="([0-9a-f]+)"', XML)}
CAVE = 0x2338000
FIND_LEVEL_GHOSTS = EDITION['game']['find_level_ghosts']
ADD_STAT, G_PLAYERS, G_STATS = (EDITION['game'][k] for k in ('add_stat', 'g_players', 'g_stats'))
STAT_NAMES = {EDITION['game'][name]: name for name in ('beat_ntropy_ghost', 'beat_oxide_ghost', 'beat_velo_ghost',
                                                      'beat_dev_ghost')}
STATS_OBJECT, PLAYERS = 0x2aa5000, 0x2ad2000
DATA, STACK, RETURN = 0x10000000, 0x20000000, 0x30000000


def ghost_file(seconds):
    return f'data:\\Ghosts\\t112_roos_tubest112_roos_tubes-{seconds:.6f}-.igb'


# Roo's Tubes in the game: N. Tropy, Oxide, Velo, Developer
ROOS = [ghost_file(t) for t in (94.195679, 83.653442, 79.178345, 76.877319)]


def run(index, raced, my_time, files=ROOS, have_level=True, player_types=(3,), stats=None):
    """Index of the track record after the race and the _unlockedNewGhost flag. Stat calls go to
    `stats` as (name, player number in player_types or None)."""
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    for base in (CAVE & ~0xfff, FIND_LEVEL_GHOSTS & ~0xfff, DATA, STACK, RETURN, ADD_STAT & ~0xfff,
                 0x1cdb000, 0x2aa4000, 0x2ad1000):
        uc.mem_map(base, 0x2000 if base in (0x2aa4000, 0x2ad1000) else 0x10000)
    uc.mem_write(CAVE, LINES[CAVE])
    for address, name in STAT_NAMES.items():
        uc.mem_write(address, name.encode() + b'\0')
    # g_stats -> stats object; g_players -> object, +0x10 list (+0xc count, +0x20 items), item +0x20 type
    uc.mem_write(G_STATS, struct.pack('<Q', STATS_OBJECT))
    uc.mem_write(G_PLAYERS, struct.pack('<Q', PLAYERS))
    player_list, player_items = PLAYERS + 0x100, PLAYERS + 0x200
    uc.mem_write(PLAYERS + 0x10, struct.pack('<Q', player_list))
    uc.mem_write(player_list + 0xc, struct.pack('<i', len(player_types)))
    uc.mem_write(player_list + 0x20, struct.pack('<Q', player_items))
    players = [PLAYERS + 0x400 + 0x40 * i for i in range(len(player_types))]
    for i, kind in enumerate(player_types):
        uc.mem_write(player_items + 8 * i, struct.pack('<Q', players[i]))
        uc.mem_write(players[i] + 0x20, struct.pack('<I', kind))
    uc.mem_write(ADD_STAT, b'\xc3')                            # ret

    manager, record, entry, ghost_list, items, ghosts = (DATA + 0x100 * i for i in range(6))
    names = DATA + 0x2000
    uc.mem_write(manager + 0x30, b'\0')
    uc.mem_write(manager + 0x34, struct.pack('<i', raced))
    uc.mem_write(record + 0xc, struct.pack('<i', index))
    uc.mem_write(entry + 0x20, struct.pack('<Q', ghost_list))
    uc.mem_write(ghost_list + 0xc, struct.pack('<i', len(files)))
    uc.mem_write(ghost_list + 0x20, struct.pack('<Q', items))
    for i, name in enumerate(files):
        ghost, text = ghosts + 0x30 * i, names + 0x100 * i
        uc.mem_write(items + 8 * i, struct.pack('<Q', ghost))
        uc.mem_write(ghost + 0x20, struct.pack('<f', 999.0))     # as in the game's table
        uc.mem_write(ghost + 0x28, struct.pack('<Q', text))
        uc.mem_write(text, name.encode() + b'\0')
    # find_level_ghosts: "mov rax, entry (or 0); ret"
    uc.mem_write(FIND_LEVEL_GHOSTS, b'\x48\xb8' + struct.pack('<Q', entry if have_level else 0) + b'\xc3')

    rbp = STACK + 0x8000
    uc.mem_write(rbp - 0x40, struct.pack('<Q', record))
    uc.mem_write(rbp - 0x70, struct.pack('<f', my_time))
    uc.mem_write(rbp - 0x80, struct.pack('<Q', DATA + 0x800))
    rsp = rbp - 0x100 - 8                   # the caller's body is 16-byte aligned; then the call
    uc.mem_write(rsp, struct.pack('<Q', RETURN))
    for reg, value in ((UC_X86_REG_RBP, rbp), (UC_X86_REG_RSP, rsp), (UC_X86_REG_R13, manager),
                       (UC_X86_REG_RAX, 0x1111111111111101), (UC_X86_REG_RBX, 0x2222), (UC_X86_REG_R12, 0x3333),
                       (UC_X86_REG_R14, 0x4444), (UC_X86_REG_R15, 0x5555)):
        uc.reg_write(reg, value)

    misaligned, calls = [], []
    def on_call(uc, address, size, _):
        if (uc.reg_read(UC_X86_REG_RSP) + 8) % 16:
            misaligned.append(address)
        if address == ADD_STAT:
            # the game's call: (stats, name, player, 0, 0, 1)
            r = [uc.reg_read(x) for x in (UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX, UC_X86_REG_RCX,
                                          UC_X86_REG_R8, UC_X86_REG_R9)]
            assert r[0] == STATS_OBJECT and r[3] == 0 and r[4] == 0 and r[5] & 0xffffffff == 1, 'bad stat call'
            calls.append((STAT_NAMES[r[1]], players.index(r[2]) if r[2] else None))
            # the call may change every caller-saved register
            for x in (UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX, UC_X86_REG_RCX, UC_X86_REG_R8, UC_X86_REG_R9):
                uc.reg_write(x, 0xdead)
    uc.hook_add(UC_HOOK_CODE, on_call, begin=FIND_LEVEL_GHOSTS, end=FIND_LEVEL_GHOSTS)
    uc.hook_add(UC_HOOK_CODE, on_call, begin=ADD_STAT, end=ADD_STAT)
    uc.emu_start(CAVE, RETURN, count=100000)

    assert uc.reg_read(UC_X86_REG_RSP) == rsp + 8, 'did not return'
    assert not misaligned, 'stack not 16-byte aligned at the call'
    assert uc.reg_read(UC_X86_REG_RAX) == 0x1111111111111101, 'rax (al) not kept'
    assert [uc.reg_read(x) for x in (UC_X86_REG_RBX, UC_X86_REG_R12, UC_X86_REG_R14, UC_X86_REG_R15)] == \
        [0x2222, 0x3333, 0x4444, 0x5555], 'rbx/r12/r14/r15 not kept'
    if stats is not None:
        stats.extend(calls)
    new_index, = struct.unpack('<i', uc.mem_read(record + 0xc, 4))
    return new_index, uc.mem_read(manager + 0x30, 1)[0]


def real_ghost_table():
    """{level name: [ghost file names]} from the game's newest GhostData.igz, or None."""
    sys.path.insert(0, str(GAME / 'scripts'))
    try:
        from archive_reader import Archive
        from igz_file import Igz
        blob = None
        for pak in ('update2', 'update', 'permanent'):   # the newest update wins
            path = GAME / f'orig/CUSA13795/archives/{pak}.pak'
            if path.is_file():
                archive = Archive(path)
                found = [f for f in archive.files if f['path'].lower() == 'loosedata/ghostdata.igz']
                if found:
                    blob = bytes(archive.extract(found[0]))
                    break
    except ImportError:
        return None
    if blob is None:
        return None
    igz = Igz(blob)
    table = {}
    for off, kind in igz.objects():
        # One entry has no level name and no ghosts; the game's lookup skips it too.
        if kind == 'CChallengeGhostData' and off + 0x10 in igz.sites['RSTT']:
            ghost_list = igz.u64(off + 0x20)
            array = igz.u64(ghost_list + 0x20) & 0xffffffff
            table[igz.string_at(off + 0x10)] = [igz.string_at((igz.u64(array + 8 * i) & 0xffffffff) + 0x28)
                                                for i in range(igz.u32(ghost_list + 0xc))]
    return table


class BeatAll(unittest.TestCase):
    def test_owner_race(self):
        # The owner's run: 1:17.99 against Velo (1:19.17); Developer is 1:16.87 and stays unbeaten.
        self.assertEqual(run(index=2, raced=2, my_time=77.99), (3, 1))

    def test_owner_example(self):
        # Race N. Tropy and beat Tropy, Oxide and Velo in one run.
        self.assertEqual(run(index=0, raced=0, my_time=78.0), (3, 1))

    def test_faster_than_all(self):
        self.assertEqual(run(index=0, raced=0, my_time=76.0), (4, 1))

    def test_only_the_raced_ghost(self):
        # Slower than Oxide: the game's own step only.
        self.assertEqual(run(index=0, raced=0, my_time=90.0), (1, 1))

    def test_no_ghost_yet(self):
        # First run beats the track's unlock time and also Tropy's time.
        self.assertEqual(run(index=-1, raced=-1, my_time=90.0), (1, 1))

    def test_no_ghost_yet_slow(self):
        # Beats only the unlock time: Tropy can now be raced.
        self.assertEqual(run(index=-1, raced=-1, my_time=100.0), (0, 1))

    def test_raced_an_older_ghost(self):
        # Velo can be raced (index 2) but you raced Tropy; you were also faster than Velo.
        self.assertEqual(run(index=2, raced=0, my_time=79.0), (3, 1))

    def test_nothing_new(self):
        self.assertEqual(run(index=2, raced=0, my_time=80.0), (2, 0))

    def test_all_beaten(self):
        self.assertEqual(run(index=4, raced=3, my_time=70.0), (4, 0))

    def test_level_not_found(self):
        # No ghost list for this level: the game's own step only.
        self.assertEqual(run(index=0, raced=0, my_time=70.0, have_level=False), (1, 1))

    def test_bad_file_names(self):
        # A name without the time stops there, as if that ghost were not beaten.
        for bad in ('', 'x', 'data:\\Ghosts\\ghost.igb', 'data:\\Ghosts\\a-1x2-.igb', '79.0-.igb', 'a-79.0-.IGB'):
            with self.subTest(bad=bad):
                self.assertEqual(run(index=1, raced=1, my_time=70.0, files=ROOS[:2] + [bad] + ROOS[3:]), (2, 1))

    def stats(self, **race):
        found = []
        run(stats=found, **race)
        return found

    def test_stats_for_skipped_ghosts(self):
        # The game counts the raced ghost itself; the patch adds the others it marks beaten.
        self.assertEqual(self.stats(index=0, raced=0, my_time=78.0), [('beat_oxide_ghost', 0), ('beat_velo_ghost', 0)])
        self.assertEqual(self.stats(index=0, raced=0, my_time=76.0),
                         [('beat_oxide_ghost', 0), ('beat_velo_ghost', 0), ('beat_dev_ghost', 0)])
        self.assertEqual(self.stats(index=2, raced=0, my_time=79.0), [('beat_velo_ghost', 0)])
        self.assertEqual(self.stats(index=-1, raced=-1, my_time=90.0), [('beat_ntropy_ghost', 0)])

    def test_no_extra_stats(self):
        for race in (dict(index=2, raced=2, my_time=77.99), dict(index=0, raced=0, my_time=90.0),
                     dict(index=-1, raced=-1, my_time=100.0), dict(index=2, raced=0, my_time=80.0),
                     dict(index=4, raced=3, my_time=70.0), dict(index=0, raced=0, my_time=70.0, have_level=False)):
            with self.subTest(**race):
                self.assertEqual(self.stats(**race), [])

    def test_owner_mystery_caves(self):
        # The owner's run: only N. Tropy unlocked, raced him, 2:01.25. Developer is 2:00.62.
        caves = [f'data:\\Ghosts\\t113_mystery_cavest113_mystery_caves-{t:.6f}-.igb'
                 for t in (144.450928, 134.005127, 128.365356, 120.624634)]
        found = []
        self.assertEqual(run(index=0, raced=0, my_time=121.25, files=caves, stats=found), (3, 1))
        self.assertEqual(found, [('beat_oxide_ghost', 0), ('beat_velo_ghost', 0)])

    def test_stat_player(self):
        # As the game picks it: the first player of type 7 or lower, else the first of 8 or higher
        race = dict(index=0, raced=0, my_time=80.0)
        self.assertEqual(self.stats(player_types=(9, 2, 5), **race), [('beat_oxide_ghost', 1)])
        self.assertEqual(self.stats(player_types=(12, 9), **race), [('beat_oxide_ghost', 0)])
        self.assertEqual(self.stats(player_types=(), **race), [('beat_oxide_ghost', None)])

    def test_real_ghost_table(self):
        table = real_ghost_table()
        if table is None:
            self.skipTest('game files not found')
        self.assertGreater(len(table), 30)
        for level, files in table.items():
            times = [float(name.rsplit('-', 2)[1]) for name in files]
            for raced in range(len(files)):
                for k in range(raced, len(files)):
                    # Just faster than ghosts raced..k, slower than ghost k+1: index k+1
                    mine = times[k] - 0.01
                    if k + 1 < len(files) and times[k + 1] >= mine:
                        continue    # ghost k+1 is not faster than ghost k on this track
                    with self.subTest(level=level, raced=raced, k=k):
                        self.assertEqual(run(index=raced, raced=raced, my_time=mine, files=files), (k + 1, 1))
                # Exactly the raced ghost's time does not beat it
                with self.subTest(level=level, raced=raced, tie=True):
                    self.assertEqual(run(index=raced, raced=raced + 1, my_time=times[raced], files=files)[0], raced)


if __name__ == '__main__':
    unittest.main()
