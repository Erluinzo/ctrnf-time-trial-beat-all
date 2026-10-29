# Time Trial: every ghost slower than you counts as beaten (USA CUSA13795 1.21).
#
# Called from the race-end function of the ghost manager (ELF 0xfcc430), in place of the game's
# "unlock the next ghost" step at 0xfcc890:
#     if (record.unlockedChallengeGhostIndex == manager.raced_index) record.index++
# That step moves at most one ghost per race. After it, this keeps moving to the next ghost
# while that ghost's time is slower than yours. Each ghost it marks beaten also counts in the
# player stats (beat_ntropy_ghost...), as if you had raced it: the game counts only the raced one.
#
# Index of the track record: -1 nothing, 0 Tropy can be raced, 1 Oxide, 2 Velo, 3 Developer,
# 4 all beaten. The track's _ghosts list is in the same order.
#
# Inputs from the caller's frame and registers (the caller's rbp is left unchanged):
#   [rbp-0x40] this track's saved record (+0xc unlockedChallengeGhostIndex)
#   [rbp-0x70] your race time (float)
#   [rbp-0x80] level name, as passed to find_level_ghosts in the game's own code (0xf9b8ea)
#   r13        ghost manager (+0x30 _unlockedNewGhost, +0x34 index of the ghost you raced)
#   [r13+0x34] is also the stat the game already counted for this race (0xfcc6e6).
# The caller still needs al after this returns. It sets every other caller-saved register again
# before it reads it (0xfcc8a7 on), so this code may change them.

    .intel_syntax noprefix
# Game code and data, set by build.py for each edition (ld --defsym): with .set, "[rip + name]"
# would become a fixed offset from this code instead of the data's address.
#   find_level_ghosts: level name -> {_levelName, _unlockChallengeGhostsTime, _ghosts}, or 0
#   add_stat: (stats, name, player, 0, 0, 1): adds 1 to a player stat
#   g_players -> object, +0x10 player list; g_stats -> stats object;
#   beat_ntropy_ghost, beat_oxide_ghost, beat_velo_ghost, beat_dev_ghost: the game's stat names

    .text
    .globl beat_all
beat_all:
    push rax                    # keeps al; five pushes also keep the stack 16-byte aligned
    push rbx
    push r12
    push r14
    push r15
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

    # Ghosts beaten in this race: index max(before, 0) up to the new index (-1 -> 0 only unlocks N. Tropy)
    mov r14d, r12d
    test r14d, r14d
    jns 1f
    xor r14d, r14d
1:
    mov r15d, ecx
count_stat:
    cmp r14d, r15d
    jge done
    cmp r14d, [r13+0x34]
    je 2f                       # the game counted this one
    mov edi, r14d
    call add_beat_stat
2:
    inc r14d
    jmp count_stat

done:
    pop r15
    pop r14
    pop r12
    pop rbx
    pop rax
    ret

# Adds 1 to the "beat ghost" stat of ghost index edi (0 N. Tropy, 1 Oxide, 2 Velo, 3 Developer),
# the same call the game makes for the raced ghost (0xfcc704).
add_beat_stat:
    sub rsp, 8                  # keeps the stack aligned for the call
    lea rsi, [rip + beat_ntropy_ghost]
    cmp edi, 1
    jb have_name
    lea rsi, [rip + beat_oxide_ghost]
    je have_name
    lea rsi, [rip + beat_velo_ghost]
    cmp edi, 3
    jb have_name
    lea rsi, [rip + beat_dev_ghost]
    ja stat_done
have_name:
    # The player, as the game picks it: the first one of type 7 or lower (+0x20), else the
    # first one of type 8 or higher, else none
    mov rdi, [rip + g_stats]
    xor edx, edx
    mov rax, [rip + g_players]
    test rax, rax
    jz call_add
    mov rax, [rax+0x10]
    test rax, rax
    jz call_add
    movsxd r8, dword ptr [rax+0xc]
    mov r9, [rax+0x20]
    test r9, r9
    jz call_add
    xor r10d, r10d
find_low:
    cmp r10, r8
    jge low_none
    mov r11, [r9+r10*8]
    inc r10
    test r11, r11
    jz find_low
    cmp dword ptr [r11+0x20], 7
    ja find_low
    mov rdx, r11
    jmp call_add
low_none:
    xor r10d, r10d
find_high:
    cmp r10, r8
    jge call_add
    mov r11, [r9+r10*8]
    inc r10
    test r11, r11
    jz find_high
    cmp dword ptr [r11+0x20], 8
    jb find_high
    mov rdx, r11
call_add:
    xor ecx, ecx
    xor r8d, r8d
    mov r9d, 1
    call add_stat
stat_done:
    add rsp, 8
    ret
