# CTRNF-Mods

Onur's mods for Crash Team Racing Nitro-Fueled on the OCTR PC port
([Ryu7w7/OCTR-NitroFueled-PC](https://github.com/Ryu7w7/OCTR-NitroFueled-PC)).

| Mod | What it does |
|---|---|
| [time-trial-beat-all](time-trial-beat-all/) | One Time Trial run unlocks every ghost slower than your time (USA and EU 1.21: one ZIP each) |

## Layout
- `<mod>/package/`: what goes into the USA mod ZIP (`mod.json`, `README.txt`, `patches/`); `<mod>/package-eu/`: the EU ZIP
  (made by build.py from `package/`, own id `<id>-eu`: the launcher needs one ZIP per game edition)
- `<mod>/src/`: assembly source of new game code
- `<mod>/build.py`: builds the patch XML from the source; `<mod>/test_*.py`: emulator tests
- `tools/eu_map.py`: finds the EU address of a USA address
- `tools/elf_look.py`: find texts, references, calls and functions in the game executable
- `notes/`: what was found in the game code

## Build a mod
Needs the OCTR checkout next to this folder (`../CTRNF`, with `out/eboot.elf` from a build),
binutils (`as`, `ld`, `objcopy`) and `pip install unicorn capstone`.

```sh
cd time-trial-beat-all
python3 build.py                 # writes package/ (USA) and package-eu/ (EU)
python3 test_beat_all.py; EU=1 python3 test_beat_all.py
python3 ../../CTRNF/scripts/package_mod.py package --output ../dist/time-trial-beat-all-<version>.zip
python3 ../../CTRNF/scripts/package_mod.py package-eu --output ../dist/time-trial-beat-all-eu-<version>.zip
```
The EU executable is read from `../CTRNF/orig/CUSA14876-eboot.elf`; EU addresses come from `tools/eu_map.py`.

No game files go into this repository or into the mods.
