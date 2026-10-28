#!/usr/bin/env python3
"""Small reverse-engineering helper for the game's executable (decrypted ELF, e.g. CTRNF/out/eboot.elf).

Addresses are the ELF's virtual addresses, which are also the patch XML addresses.

  elf_look.py ELF str TEXT          where TEXT is stored, and the code that loads its address
  elf_look.py ELF refs ADDR         code that loads ADDR (RIP-relative lea/mov)
  elf_look.py ELF calls ADDR        call/jmp rel32 sites that go to ADDR
  elf_look.py ELF func ADDR         disassemble the whole function that holds ADDR
  elf_look.py ELF dis ADDR [COUNT]  disassemble COUNT instructions from ADDR
  elf_look.py ELF bytes ADDR LEN    raw bytes, as a Signature-style hex string
"""
import bisect, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

class Elf:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        phoff, = struct.unpack_from('<Q', self.data, 0x20)
        phnum, = struct.unpack_from('<H', self.data, 0x38)
        segs = [struct.unpack_from('<IIQQQQQQ', self.data, phoff + 56 * i) for i in range(phnum)]
        # (vaddr, offset, filesz) of the mapped segments; type 0x61000010 is the PS4 read-only data
        self.segs = [(s[3], s[2], s[5]) for s in segs if s[0] in (1, 0x61000010)]
        text = next(s for s in segs if s[0] == 1 and s[1] & 1)
        self.text_va, self.text_off, self.text_size = text[3], text[2], text[5]
        ehh = next(s for s in segs if s[0] == 0x6474e550)
        self.funcs = self._funcs(ehh[2], ehh[3])
        self.starts = [f[0] for f in self.funcs]
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64)

    def _funcs(self, off, va):
        # Function starts and sizes come from .eh_frame_hdr: every function has an FDE.
        count, = struct.unpack_from('<i', self.data, off + 8)
        out = []
        for i in range(count):
            loc, fde = struct.unpack_from('<ii', self.data, off + 12 + 8 * i)
            size, = struct.unpack_from('<i', self.data, self.off(va + fde) + 12)
            out.append((va + loc, size))
        return sorted(out)

    def off(self, va):
        for v, o, n in self.segs:
            if v <= va < v + n:
                return o + va - v
        raise ValueError(f'{va:#x} is not in the file')

    def va(self, off):
        for v, o, n in self.segs:
            if o <= off < o + n:
                return v + off - o
        return None

    def func(self, va):
        i = bisect.bisect_right(self.starts, va) - 1
        if i >= 0 and va < self.funcs[i][0] + self.funcs[i][1]:
            return self.funcs[i]
        return None

    def read(self, va, n):
        o = self.off(va)
        return self.data[o:o + n]

    def dis(self, va, n=None, count=40):
        code = self.read(va, n if n else count * 15)
        insns = list(self.cs.disasm(code, va))
        return insns if n else insns[:count]

    def refs(self, target):
        # RIP-relative operand: the 4-byte displacement is followed by the end of the instruction,
        # or by an immediate of 1 or 4 bytes ("cmp byte [rip+x], 0" has one).
        t = self.data[self.text_off:self.text_off + self.text_size]
        hits = set()
        for i in range(len(t) - 4):
            d, = struct.unpack_from('<i', t, i)
            end = self.text_va + i + 4
            for imm in (0, 1, 4):
                if end + imm + d == target:
                    hits.add(self.text_va + i)
        return sorted(hits)

    def calls(self, target):
        t = self.data[self.text_off:self.text_off + self.text_size]
        out = []
        for op in (b'\xe8', b'\xe9'):
            i = t.find(op)
            while i != -1:
                if i + 5 <= len(t):
                    d, = struct.unpack_from('<i', t, i + 1)
                    if self.text_va + i + 5 + d == target:
                        out.append(self.text_va + i)
                i = t.find(op, i + 1)
        return sorted(out)

def name(elf, va):
    f = elf.func(va)
    return f'func {f[0]:#x}+{va - f[0]:#x}' if f else 'no func'

def show(insns):
    for x in insns:
        print(f'  {x.address:#9x}  {x.bytes.hex():<24} {x.mnemonic} {x.op_str}')

def main():
    elf, cmd, args = Elf(sys.argv[1]), sys.argv[2], sys.argv[3:]
    if cmd == 'str':
        needle = args[0].encode()
        i = elf.data.find(needle)
        while i != -1:
            va = elf.va(i)
            if va is not None and elf.data[i - 1] == 0:
                print(f'"{args[0]}" at {va:#x}')
                for r in elf.refs(va):
                    print(f'  used at {r:#x} ({name(elf, r)})')
            i = elf.data.find(needle, i + 1)
    elif cmd == 'refs':
        for r in elf.refs(int(args[0], 0)):
            print(f'{r:#x} ({name(elf, r)})')
    elif cmd == 'calls':
        for r in elf.calls(int(args[0], 0)):
            print(f'{r:#x} ({name(elf, r)})')
    elif cmd == 'func':
        f = elf.func(int(args[0], 0))
        print(f'function {f[0]:#x}, {f[1]} bytes')
        show(elf.dis(f[0], f[1]))
    elif cmd == 'dis':
        show(elf.dis(int(args[0], 0), count=int(args[1]) if len(args) > 1 else 40))
    elif cmd == 'bytes':
        print(elf.read(int(args[0], 0), int(args[1], 0)).hex(' '))
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main()
