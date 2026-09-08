# Bard balance audit — 8 September 2026

Review baseline: `0dc6050` on this fork, including the merged Skald, Dancer and
Jester changes. Upstream `TheArtisanBG/Bardic-Wonders` was fetched during the
review; `4e72d97` was its latest master commit and was already an ancestor of
the fork. No upstream merge was needed.

## Scope and decisions

The review covered all eleven Bard kits: Blade, Jester, Skald, Abettor, Dancer,
Darkbloom, Storm Drummer, Troubadour, Deathsinger, Strategist and Kapellmeister,
plus their shared HLAs and Inspirations. It inspected installer actions, SPL
effects and delivery resources, level grants and HLA limits. This is a source
and resource audit, not a claim of live gameplay acceptance or exhaustive mod
compatibility. Gallant is a Paladin kit and was not separately rebalanced;
where it uses the same shared HLA resources, it receives their corrections.

| Ability | Confirmed resource behavior before this release | Decision |
|---|---|---|
| Legionnaire's March | Sets every recipient's base THAC0 to 0 for 60 seconds, plus damage and APR bonuses | Replace only the THAC0 setting with a +4 additive bonus; retain duration, APR rules, +4 damage and selection limit |
| Thunderclap | At level 10, 60-second stun on a failed save at -4 and 60-second, unsaved 50% spell failure; affects allies too | Limit stun, deafness and spell failure to 12 seconds; retain save, friendly fire and one daily use |
| Darkbloom enhanced song | Sets enemy MR to 0 and grants +6 arcane caster levels to allies | Reduce MR by 50 percentage points and grant +3 arcane caster levels; retain the rest of the song |
| Dark Entanglement | Poison effect has a full probability window and lasts 12 seconds despite the description's 10% chance for 5 seconds | Match the existing description |
| Darkbloom acid backstab | Rolls 8d2 despite the description's 2d8 | Match the description; average damage falls from 12 to 9 |
| Resonating Weapon | Rolls 6d2 despite the description's 2d6 | Match the description; average wave damage falls from 9 to 7; retain cascading waves and the previous stun nerf |
| Hymn of Requiem | Damage has a saving throw, but its special field is 2 (reverse HP drain), not 256 (save for half) | Replace the incorrect flag; retain 6d10 damage/healing and existing delivery |

The spell-effect meanings were checked against [IESDP's EE opcode reference](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm).
For descending THAC0, positive additive opcode 54 values represent a bonus;
this was cross-checked against the mod's existing bonuses and
[GemRB's reverse-THAC0 modifier handling](https://github.com/gemrb/gemrb/blob/master/gemrb/core/Scriptable/CombatInfo.cpp).

No further immediate numerical reductions were justified for the already
rebalanced Skald, Dancer, Jester or Abettor, or for Troubadour, Deathsinger,
Kapellmeister and Inspirations. Some large bonuses have substantial costs:
Deathsinger's enhanced song, for example, prevents attacking and casting while
its summons operate. High numbers alone were not treated as a defect.

## Follow-up candidates, unchanged in this release

These require targeted investigation before changing mechanics. Their presence
here is not a claim that a live exploit has been reproduced.

| Area | Static evidence | Next check |
|---|---|---|
| Blade Defensive Spin | All ten `SPCL522` ability headers require level 1 despite increasing AC values | Confirm which header the engine selects at levels 1, 5 and 10; compare resulting AC with the intended progression |
| Blade improved parry | `SPCL522A` removes the normal spin resources but does not name `C0BLDH2A`; both spins use broad damage-opcode immunity | Observe one melee hit, another melee hit, a missile and a spell during each spin; verify the improved parry ends and define its intended damage coverage before redesigning it |
| Resonating Weapon | No explicit self-resource refresh precedes its melee/ranged on-hit grants | Compare one cast with two overlapping casts at fixed APR and enemy spacing; count waves per successful hit |
| Jester / Kapellmeister enhanced songs | Their refresh effects name the ordinary song resources rather than their own enhanced payloads | Track bonuses/debuffs across multiple pulses, with and without Lingering Song and component 2004; check for overlapping applications |
| Lingering Song | Component 2004 sets the duration modifier to 130%, while the reverse install order can end at 140%; its four-round description differs from percentage scaling | Test both component orders and distinguish controller duration from payload duration before choosing a unified behavior |
| Strategist Checkmate | Intelligence-based save penalty can reach -9; actual duration is 200 ticks, while descriptions disagree between one and two rounds | Test high-Intelligence use against equal-Intelligence and lower-Intelligence enemies; weigh its single daily level-20 use and party Improved Haste |
| Darkbloom healing | Enhanced song uses opcode 17 percentage healing while its description says regeneration based on maximum HP | Observe healing at low and high current HP on consecutive song pulses |

Known compatibility work remains separate: [Darkbloom spell imports under SR (#2)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/2),
[other priest-spell clones (#3)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/3),
[New Bard Spells / Gallant component order (#4)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/4),
and [Symphony party invisibility (#5)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/5).
The balance changes do not resolve those issues or remove the Darkbloom SR exclusion.

## Verification and focused playtest

Release checks passed: **108 automated tests** and **41 WeiDU 249 syntax
checks** (the main TP2 and all library TPAs).

Automated checks run the production resource actions with WeiDU 249 in
disposable fixtures, inspect installed effect fields and descriptions, preserve
unrelated bytes, and verify restoration on uninstall. Shared HLA fixtures also
exercise real projectile registration and reinstall stability. The main TP2
and library TPAs receive separate syntax checks. These fixtures do not execute
the entire game or every kit-registration path.

Before calling the release live accepted, test in a disposable installation:

1. Legionnaire's March: a warrior and a non-warrior gain exactly +4 to hit and
   +4 damage, appropriate APR behavior, and lose the benefits after one turn.
2. Thunderclap: successful and failed saves; two-round expiration of stun and
   spell failure; friendly-fire behavior remains intact.
3. Darkbloom: compare enemy MR above and below 50%, check +3 ally arcane caster
   levels, poison frequency/duration and acid backstab damage. Use a supported
   spell setup, not the excluded SR combination.
4. Hymn: successful saves halve damage, failed saves take full damage, and the
   caster does not lose HP through reverse drain. Ally healing remains 6d10.
5. Resonating Weapon: each wave rolls 2d6 and the existing stun chance/save and
   cascading behavior remain functional.
6. Previously merged changes: verify Skald song defense, Dancer AC progression,
   and Jester song/Heckle/Mad Ramble values in the same installation.

No live game or save was modified during this review. The separate Abettor tail
installer remains version 1.0.0 and does not apply these additional changes to
an existing stacked playthrough.
