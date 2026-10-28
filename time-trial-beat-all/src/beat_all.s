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
# The caller still needs al after this returns.

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
    vmovss xmm1, [rsi+0x20]     # this ghost's _time
    vucomiss xmm1, xmm0
    jbe save                    # this ghost is not slower than you (or its time is not a number)
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
