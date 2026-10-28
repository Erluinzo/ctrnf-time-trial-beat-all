# Time Trial ghosts: findings (USA CUSA13795 1.21)

Addresses are ELF addresses of `CTRNF/out/eboot.elf`; patch XML addresses are these + 0x400000.
The owner's game (the 1.21 build for firmware 6.72+) has the same layout as the reference build:
every built-in patch signature matches at its stated address.

## How the field names were found
The game registers its class fields with name tables (Alchemy engine reflection). A registration
call gets `lea rsi, names` (8-byte string pointers), `lea rdx, ...` and `lea rcx, offsets` (2-byte
field offsets in the same order). `tools/elf_look.py ELF str NAME` finds the name, then search
the data for the pointer to it to find its table.

## Classes
Ghost manager (singleton; `r13` in the race-end function):

| Offset | Field |
|---|---|
| +0x0c | _isRecording |
| +0x10 | _recordTime |
| +0x28 | _recordingGhost (your ghost; its `_time` at +0x28 is your race time) |
| +0x30 | _unlockedNewGhost (the "new ghost" message) |
| +0x34 | _highestPlayingChallengeGhostIndex (ghost you raced; -1 none) |
| +0x38 | _highestPlayingChallengeGhostTime (its time; with no ghost: the track's unlock time) |
| +0x40 | _playingGhosts |
| +0x50 | _challengeGhostToLoad |
| +0x58 | _unlockedNTropy |

Saved per-track record: +0x0c `unlockedChallengeGhostIndex`, +0x10 `_ghost`.
Index: -1 nothing, 0 N. Tropy can be raced, 1 Oxide, 2 Velo, 3 Developer, 4 all beaten.

Static challenge ghost table (`_challengeGhosts` at +0x10 of the object from 0xf9ba00):
- per track: +0x10 `_levelName`, +0x18 `_unlockChallengeGhostsTime` (float), +0x20 `_ghosts`
- per ghost: +0x10 `_kartName`, +0x18 `_driverName`, +0x20 `_time` (float), +0x28 `_ghostFile`
- lists: +0x0c count, +0x20 pointer array. `_ghosts` order = index (Tropy, Oxide, Velo, Developer).

The ghost files (`orig/CUSA13795/ghosts/*.igb`) also hold the time, as `ghost_time` and in the
file name.

## Functions
| ELF | What |
|---|---|
| 0xf9b970 | level name -> per-track challenge entry, or 0 (plain string compare loop) |
| 0xf9b250 | race start: sets +0x34 = -1, +0x38 = FLT_MAX, or the unlock time when no ghost is loaded |
| 0xf9b7f0 | a challenge ghost loaded: sets +0x34/+0x38 to the fastest playing ghost |
| 0xfcc430 | race end: stats `beat_*_ghost` (jump table on +0x34), then at 0xfcc890 `if (record.index == raced) record.index++` |

In 0xfcc430 at 0xfcc890: `[rbp-0x40]` record, `[rbp-0x70]` your time, `[rbp-0x80]` level name,
`al` still needed afterwards. Only 0xfcc890 and 0xfcc8a7 are jump targets in 0xfcc890-0xfcc8a7.

## Free space for new code
Zero padding at ELF 0x2317810-0x233c078 in the code segment: no instruction or relocated pointer
refers to it. tomtotom's drift gauge uses 0x2317820-0x23192df. This mod: 0x2338000.

## Open
- Unlock Everything (`patch_unlock_all`) changes 18 unlock-condition functions; not checked
  whether they show all ghosts. Test this mod with it off.
- Trophies 25/26 ("beat every N. Tropy / Oxide time") and Pit Stop challenges: not checked
  whether they read the record index or the `beat_*_ghost` stats (the mod does not add stats
  for skipped ghosts).
