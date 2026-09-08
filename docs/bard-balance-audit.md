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
| Legionnaire's March | Sets every recipient's base THAC0 to 0 for 60 seconds, plus damage and APR bonuses | Replace the THAC0 setting with a +3 additive bonus and shorten all buffs/APR exclusions to 18 seconds; retain APR rules, +4 damage and selection limit |
| Thunderclap | At level 10, 60-second stun on a failed save at -4 and 60-second, unsaved 50% spell failure; affects allies too | Limit stun to 6 seconds and deafness/spell failure to 12 seconds at 25%; retain save, friendly fire and one daily use |
| Darkbloom enhanced song | Sets enemy MR to 0 and grants +6 arcane caster levels to allies | Reduce MR by 50 percentage points, grant +3 arcane caster levels and +1 casting speed; retain the rest of the song |
| Dark Entanglement | Poison effect has a full probability window and lasts 12 seconds despite the description's 10% chance for 5 seconds | Match the existing description |
| Darkbloom acid backstab | Rolls 8d2 despite the description's 2d8 | Match the description; average damage falls from 12 to 9 |
| Resonating Weapon | Each overlapping wave carries a one-round stun check; damage rolls 6d2 despite the description's 2d6 | Remove stun and its icon; retain five rounds of cascading 2d6 damage and eight HLA selections |
| Hymn of Requiem | Damage has a saving throw, but its special field is 2 (reverse HP drain), not 256 (save for half) | Replace the incorrect flag; retain 6d10 damage/healing and existing delivery |
| Die Aufklärung | +2 casting speed, singer +50% MR/+10 spell saves, and missing self refresh across 100-tick effects/90-tick pulses | Correct singer/recipient refresh; reduce speed to +1, singer MR to +25% and spell saves to +5; retain +4 INT/arcane caster levels and existing spell recovery |
| Checkmate | INT-based save modifier reaches -9; stun and party Improved Haste last 200 ticks, ignoring MR and dispelling | Cap the modifier at -3, stun for 90 ticks (one round), Improved Haste for 180 ticks (two rounds); retain INT selection and level-20 daily use |

The spell-effect meanings were checked against [IESDP's EE opcode reference](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm).
For descending THAC0, positive additive opcode 54 values represent a bonus;
this was cross-checked against the mod's existing bonuses and
[GemRB's reverse-THAC0 modifier handling](https://github.com/gemrb/gemrb/blob/master/gemrb/core/Scriptable/CombatInfo.cpp).

No further immediate numerical reductions were justified for the already
rebalanced Skald, Dancer, Jester or Abettor, or for Troubadour, Deathsinger
and Inspirations. Some large bonuses have substantial costs:
Deathsinger's enhanced song, for example, prevents attacking and casting while
its summons operate. High numbers alone were not treated as a defect.

## Follow-up candidates, unchanged in this release

These require targeted investigation before changing mechanics. Their presence
here is not a claim that a live exploit has been reproduced.

Casting-speed bonuses already stack: Prestissimo and Unchained Voice each give
+1 permanently; the unkitted Bard's Inspire Alacrity gives allies +1, or +2 at
level 40. Darkbloom's revised +1 song bonus can combine with those sources.
Other kits also have casting-speed effects, including Skald's conditional Combat
Casting, Strategist's enhanced song and Kapellmeister's song/cadence.

| Area | Static evidence | Next check |
|---|---|---|
| Blade Defensive Spin | All ten `SPCL522` ability headers require level 1 despite increasing AC values | Confirm which header the engine selects at levels 1, 5 and 10; compare resulting AC with the intended progression |
| Blade improved parry | `SPCL522A` removes the normal spin resources but does not name `C0BLDH2A`; both spins use broad damage-opcode immunity | Observe one melee hit, another melee hit, a missile and a spell during each spin; verify the improved parry ends and define its intended damage coverage before redesigning it |
| Resonating Weapon | No explicit self-resource refresh precedes its melee/ranged on-hit grants | Compare one cast with two overlapping casts at fixed APR and enemy spacing; count waves per successful hit |
| Jester enhanced song | Its refresh effects name the ordinary song rather than its own enhanced payload | Track bonuses/debuffs across multiple pulses, with and without Lingering Song and component 2004; check for overlapping applications |
| Kapellmeister spell recovery | The enhanced branch restores up to level 5 at nominal 51%, with a conditional second restoration up to level 8 at nominal 9%; the prior description promised two 30% rolls up to level 8 | Decide spell-recovery strength explicitly; matching the old description would increase high-level restoration |
| Lingering Song | Component 2004 sets the duration modifier to 130%, while the reverse install order can end at 140%; its four-round description differs from percentage scaling | Test both component orders and distinguish controller duration from payload duration before choosing a unified behavior |
| Strategist low-INT fallback | When current INT is below 16, the fallback still excludes enemies at INT 16, rather than at the caster's current score | Test temporary INT reduction before changing dispatch; the ordinary INT 16–25 selection behavior is preserved |
| Darkbloom healing | Enhanced song uses opcode 17 percentage healing while its description says regeneration based on maximum HP | Observe healing at low and high current HP on consecutive song pulses |

Known compatibility work remains separate: [Darkbloom spell imports under SR (#2)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/2),
[other priest-spell clones (#3)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/3),
[New Bard Spells / Gallant component order (#4)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/4),
and [Symphony party invisibility (#5)](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/5).
The balance changes do not resolve those issues or remove the Darkbloom SR exclusion.

## Verification and focused playtest

All 116 automated tests passed. WeiDU 24900 also passed 42 syntax checks:
the main TP2 and all library TPAs.

Automated checks run the production resource actions with WeiDU 249 in
disposable fixtures, inspect installed effect fields and descriptions, preserve
unrelated bytes, and verify restoration on uninstall. Shared HLA fixtures also
exercise real projectile registration and reinstall stability. The main TP2
and library TPAs receive separate syntax checks. These fixtures do not execute
the entire game or every kit-registration path.

Before calling the release live accepted, test in a disposable installation:

1. Legionnaire's March: a warrior and a non-warrior gain exactly +3 to hit and
   +4 damage, appropriate APR behavior, and lose the benefits after three rounds.
2. Thunderclap: successful and failed saves; one-round expiration of stun and
   two-round expiration of 25% spell failure; friendly-fire behavior remains intact.
3. Darkbloom: compare enemy MR above and below 50%, check +3 ally arcane caster
   levels and +1 casting speed, poison frequency/duration and acid backstab damage. Use a supported
   spell setup, not the excluded SR combination.
4. Hymn: successful saves halve damage, failed saves take full damage, and the
   caster does not lose HP through reverse drain. Ally healing remains 6d10.
5. Resonating Weapon: each wave rolls 2d6, no stun or stun icon is applied, and
   cascading behavior remains functional.
6. Kapellmeister: follow singer and ally stats across multiple pulses with and
   without component 2004; verify refreshed +4 INT/arcane levels, +1 casting speed,
   singer +25% MR/+5 spell saves, expiration, and unchanged spell recovery.
7. Checkmate: compare INT 16, 18, 19 and 25; confirm the save penalty caps at -3,
   equal/higher-INT enemies remain excluded, stun lasts one round and party
   Improved Haste lasts two rounds.
8. Previously merged changes: verify Skald song defense, Dancer AC progression,
   and Jester song/Heckle/Mad Ramble values in the same installation.

No live game or save was modified during this review. The separate Abettor tail
installer remains version 1.0.0 and does not apply these additional changes to
an existing stacked playthrough.
