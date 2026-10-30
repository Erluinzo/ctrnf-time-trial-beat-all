# Time Trial: Beat Every Ghost at Once

One Time Trial race in CTR Nitro-Fueled ([OCTR PC port](https://github.com/Ryu7w7/OCTR-NitroFueled-PC))
counts every ghost on the track slower than your time (the game alone unlocks one ghost per race).

Offline only. Back up your save first.

## Install
Download the ZIP for your game from [Releases](https://github.com/Erluinzo/ctrnf-time-trial-beat-all/releases):
`time-trial-beat-all` (USA, CUSA13795) or `time-trial-beat-all-eu` (EU, CUSA14876), version 1.21.
In the launcher: Mods > Add files, enable it, restart the game.

## Build
Needs the OCTR checkout at `../CTRNF`, binutils, `pip install unicorn capstone`:
`cd time-trial-beat-all && python3 build.py && python3 test_beat_all.py`.

## License
MIT. Copyright (c) 2026 Onur.
