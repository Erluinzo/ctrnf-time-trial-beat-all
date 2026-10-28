# Time Trial: every ghost slower than you counts as beaten (USA CUSA13795 1.21).
#
# Called from the race-end function of the ghost manager (ELF 0xfcc430), in place of the game's
# "unlock the next ghost" step at 0xfcc890:
#     if (record.unlockedChallengeGhostIndex == manager.raced_index) record.index++
# That step moves at most one ghost per race. After it, this keeps moving to the next ghost
# while that ghost's time is slower than yours.
#
# Index of the track record: -1 nothing, 0 Tropy can be raced, 1 Oxide, 2 Velo, 3 Developer,
# 4 all beaten. The track's _ghosts list is in the same order.
#
# Inputs from the caller's frame and registers (the caller's rbp is left unchanged):
#   [rbp-0x40] this track's saved record (+0xc unlockedChallengeGhostIndex)
#   [rbp-0x70] your race time (float)
#   [rbp-0x80] level name, as passed to find_level_ghosts in the game's own code (0xf9b8ea)
#   r13        ghost manager (+0x30 _unlockedNewGhost, +0x34 index of the ghost you raced)
# The caller still needs al after this returns. It sets every other caller-saved register again
# before it reads it (0xfcc8a7 on), so this code may change them.

    .intel_syntax noprefix
    .set find_level_ghosts, 0xf9b970    # level name -> {_levelName, _unlockChallengeGhostsTime, _ghosts}, or 0

    .text
    .globl beat_all
beat_all:
    push rax                    # keeps al; three pushes also keep the stack 16-byte aligned
    push rbx
    push r12
    mov rbx, [rbp-0x40]
    mov r12d, [rbx+0xc]         # index before this race

    # The game's own step
    mov ecx, r12d
    cmp ecx, [r13+0x34]
    jne 1f
    inc ecx
1:
    test ecx, ecx
    js save                     # no ghost unlocked yet (index -1): nothing to compare with

    push rcx
    push rcx                    # twice: keeps the stack aligned for the call
    mov rdi, [rbp-0x80]
    call find_level_ghosts
    pop rcx
    pop rcx
    test rax, rax
    jz save
    mov rax, [rax+0x20]         # _ghosts
    test rax, rax
    jz save
    mov edx, [rax+0xc]          # ghost count
    mov rax, [rax+0x20]         # ghost pointers
    vmovss xmm0, [rbp-0x70]     # your time

next:
    cmp ecx, edx
    jge save
    mov rsi, [rax+rcx*8]
    test rsi, rsi
    jz save
    # The ghost's _time in this table is always 999.0. The real time is in its file name,
    # the same value the game reads from the file: "data:\Ghosts\t112_..._tubes-76.877319-.igb".
    mov rsi, [rsi+0x28]         # _ghostFile
    test rsi, rsi
    jz save
    mov r8, rsi
find_end:
    cmp byte ptr [r8], 0
    je found_end
    inc r8
    jmp find_end
found_end:
    lea r9, [rsi+6]
    cmp r8, r9
    jb save                     # too short for "-N-.igb"
    cmp dword ptr [r8-4], 0x6267692e    # ".igb"
    jne save
    cmp byte ptr [r8-5], '-'
    jne save
    lea r9, [r8-5]              # the "-" after the time
find_start:
    dec r9
    cmp r9, rsi
    jbe save                    # no "-" before the time
    cmp byte ptr [r9-1], '-'
    jne find_start

    # "76.877319": r10 = 76877319, r11 = 1000000
    xor r10d, r10d
    mov r11d, 1
    xor edi, edi                # 1 after the decimal point
read_digit:
    movzx esi, byte ptr [r9]
    inc r9
    cmp esi, '-'
    je have_time
    cmp esi, '.'
    jne digit
    mov edi, 1
    jmp read_digit
digit:
    sub esi, '0'
    cmp esi, 9
    ja save                     # not a digit
    imul r10, r10, 10
    add r10, rsi
    test edi, edi
    jz read_digit
    imul r11, r11, 10
    jmp read_digit
have_time:
    vcvtsi2sd xmm1, xmm1, r10
    vcvtsi2sd xmm2, xmm2, r11
    vdivsd xmm1, xmm1, xmm2
    vcvtsd2ss xmm1, xmm1, xmm1  # a float, as the game compares it
    vucomiss xmm1, xmm0
    jbe save                    # this ghost is not slower than you
    inc ecx
    jmp next

save:
    cmp ecx, r12d
    je done
    mov [rbx+0xc], ecx
    mov byte ptr [r13+0x30], 1  # _unlockedNewGhost: the game shows its "new ghost" message
done:
    pop r12
    pop rbx
    pop rax
    ret
