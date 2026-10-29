#!/usr/bin/env python3
"""Finds the EU 1.21 (CUSA14876) address of a USA 1.21 (CUSA13795) address in the game's executable.

  eu_map.py ADDR...            (USA ELF addresses; prints the EU address and how it was found)

Both executables have the same functions in the same order (from .eh_frame_hdr); all but one
(0xe71d60, 10 bytes shorter in EU) have the same size, moved by 0, -0x10 or -0x20. So:
- an address inside a function: the same function of EU, same offset; checked by comparing the next
  instructions (same lengths and mnemonics; jump and data targets may differ because code moved);
- any other address (data, vtables, strings, import stubs): every USA instruction that uses it
  (RIP-relative operand or call/jmp rel32) is found, mapped as above, decoded in EU, and its target
  read there. All of them must agree.
"""
import bisect, struct, sys
from pathlib import Path
import numpy as np
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elf_look import Elf

USA = Path.home() / 'Desktop/CTRNF/out/eboot.elf'
EU = Path.home() / 'Desktop/CTRNF/orig/CUSA14876-eboot.elf'
CHECK = 12          # instructions compared after a mapped code address


class Mapper:
    def __init__(self, usa=USA, eu=EU):
        self.u, self.e = Elf(usa), Elf(eu)
        assert len(self.u.funcs) == len(self.e.funcs), 'the function lists differ'
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64)
        self.cs.detail = True
        self._refs = None

    def _insns(self, elf, va, n):
        return list(self.cs.disasm(elf.data[elf.off(va):elf.off(va) + 16 * n], va))[:n]

    def _same_code(self, ua, ea, n=CHECK):
        a, b = self._insns(self.u, ua, n), self._insns(self.e, ea, n)
        return len(a) == len(b) == n and all(x.size == y.size and x.mnemonic == y.mnemonic for x, y in zip(a, b))

    def code(self, ua):
        """EU address of a USA address inside a function, or None"""
        k = bisect.bisect_right(self.u.starts, ua) - 1
        if k < 0: return None
        start, size = self.u.funcs[k]
        if not start <= ua < start + size: return None
        estart, esize = self.e.funcs[k]
        if esize != size: raise ValueError(f'{ua:#x}: its function {start:#x} has another size in EU')
        ea = estart + ua - start
        if not self._same_code(ua, ea, min(CHECK, 4)):
            raise ValueError(f'{ua:#x}: the code differs at {ea:#x}')
        return ea

    def _reference_sites(self):
        """{target: [instruction address]} of RIP-relative operands and call/jmp rel32 in USA code"""
        if self._refs is None:
            u = self.u
            text = np.frombuffer(u.data, dtype=np.uint8, count=u.text_size, offset=u.text_off)
            n = len(text) - 4
            disp = (text[:n].astype(np.int64) | text[1:n + 1].astype(np.int64) << 8 |
                    text[2:n + 2].astype(np.int64) << 16 | text[3:n + 3].astype(np.int64) << 24)
            disp = np.where(disp >= 1 << 31, disp - (1 << 32), disp)
            self._disp = disp
            self._refs = {}
        return self._disp

    def references(self, target, limit=12):
        """USA instructions whose RIP-relative operand or rel32 branch goes to target"""
        disp = self._reference_sites()
        u = self.u
        pos = np.arange(len(disp), dtype=np.int64) + u.text_va
        found = []
        # the displacement is followed by 0, 1, 2 or 4 bytes of immediate
        for imm in (0, 1, 2, 4):
            hits = np.nonzero(disp == target - (pos + 4 + imm))[0]
            for h in hits[:200]:
                at = int(pos[h])
                for back in range(1, 8):
                    for insn in self._insns(u, at - back, 1):
                        if insn.address + insn.size != at + 4 + imm: continue
                        ops = insn.op_str
                        if f'{target:#x}' in ops or 'rip' in ops:
                            if insn.mnemonic.startswith(('call', 'j')) or 'rip' in ops:
                                found.append(insn.address)
                if len(found) >= limit: return sorted(set(found))
        return sorted(set(found))

    def _eu_target(self, ea):
        insn = self._insns(self.e, ea, 1)[0]
        if 'rip' in insn.op_str:
            for op in insn.operands:
                if op.type == 3 and op.mem.base == 41:     # X86_OP_MEM, base rip
                    return insn.address + insn.size + op.mem.disp
        if insn.mnemonic.startswith(('call', 'j')) and insn.operands and insn.operands[0].type == 2:
            return insn.operands[0].imm
        raise ValueError(f'EU {ea:#x}: not a RIP or branch instruction: {insn.mnemonic} {insn.op_str}')

    def data(self, ua):
        """EU address of something code refers to, from all USA references; (address, number of references)"""
        sites = self.references(ua)
        if not sites: raise ValueError(f'{ua:#x}: no code refers to it')
        targets = set()
        for s in sites:
            ea = self.code(s)
            if ea is None: continue      # references outside functions are skipped
            targets.add(self._eu_target(ea))
        if len(targets) != 1: raise ValueError(f'{ua:#x}: references disagree: {[hex(t) for t in targets]}')
        return targets.pop(), len(sites)

    def function_diff(self, ua):
        """Differences between the USA function holding ua and its EU twin, ignoring jump/call and
        RIP-relative targets (code moved): [] when the two do the same."""
        k = bisect.bisect_right(self.u.starts, ua) - 1
        (us, size), (es, esize) = self.u.funcs[k], self.e.funcs[k]
        a = list(self.cs.disasm(self.u.data[self.u.off(us):self.u.off(us) + size], us))
        b = list(self.cs.disasm(self.e.data[self.e.off(es):self.e.off(es) + esize], es))
        diffs = [] if len(a) == len(b) else [f'{len(a)} instructions in USA, {len(b)} in EU']
        for x, y in zip(a, b):
            moved = x.mnemonic.startswith(('call', 'j')) or 'rip' in x.op_str
            if x.mnemonic != y.mnemonic or x.size != y.size or (not moved and x.op_str != y.op_str):
                diffs.append(f'{x.address:#x} {x.mnemonic} {x.op_str} | EU {y.address:#x} {y.mnemonic} {y.op_str}')
        return diffs

    def map(self, ua):
        """(EU address, how)"""
        try:
            ea = self.code(ua)
            if ea is not None: return ea, 'function'
        except ValueError:
            raise
        ea, n = self.data(ua)
        return ea, f'{n} references'


if __name__ == '__main__':
    m = Mapper()
    if sys.argv[1:2] == ['func']:       # eu_map.py func ADDR...: compare whole functions
        for a in sys.argv[2:]:
            d = m.function_diff(int(a, 16))
            print(f'{a}: same' if not d else f'{a}: {len(d)} differences', *d[:8], sep='\n  ')
        sys.exit()
    for a in sys.argv[1:]:
        ua = int(a, 16)
        try:
            ea, how = m.map(ua)
            print(f'{ua:#x} -> {ea:#x}  ({how}, shift {ea - ua:+#x})')
        except ValueError as e:
            print(f'{ua:#x}: NOT MAPPED: {e}')
