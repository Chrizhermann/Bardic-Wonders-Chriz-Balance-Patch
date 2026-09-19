# Bardic Wonders — Balance Patch

A personal balance-patch fork of [Bardic Wonders](https://github.com/TheArtisanBG/Bardic-Wonders) by **Artemius_I** (also known as **The Artisan** / **AionZ**), a fantastic mod that overhauls and expands the Bard class for BG:EE, BG2:EE, EET, and IWD:EE. All kit concepts, spell design, items, and creative direction are the original author's work; this fork adjusts balance and corrects related spell effects while keeping the spirit of each ability intact.

> [!WARNING]
> **SPELL REVISIONS COMPATIBILITY — PHASE 0**
>
> **Do not include the Darkbloom Bard kit (component `1006`) in recommended
> Spell Revisions installs or mod collections for now.** Darkbloom imports
> spells by fixed physical `SPPRxxx` filenames. Under SR, those slots can hold
> different spells: the inspected install produced Strength of Stone instead
> of Curse, Cause Moderate Wounds instead of Beast Claw, Icelance instead of
> Mold Touch, and Healing Mist instead of Mist of Eldath.
>
> This failure is local to Darkbloom's copied spell list. It is separate from
> Artisan's Kitpack Favored Soul's global priest-delivery problem and does not
> by itself rewrite Cleric, Druid, Paladin, or Ranger spellbooks.

> [!NOTE]
> **KNOWN ISSUE — SYMPHONY PARTY INVISIBILITY**
>
> Earlier live-install work supports accepting the broader Abettor kit for
> release, but there is no surviving in-engine verification of the intended
> one-round ordinary party Invisibility at the beginning and end of **Symphony
> of the Dark Children**, and it may not trigger. The remaining song changes are
> usable as released; the invisibility behavior is tracked separately in [issue
> #5](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/5).

## Credit & original author

Bardic Wonders is designed and maintained by **Artemius_I**. If you enjoy the mod, please support him directly:

- **Website:** https://theartisanbg.github.io/The-Artisans-Corner/
- **Upstream repository:** https://github.com/TheArtisanBG/Bardic-Wonders
- **Patreon:** https://www.patreon.com/Artemius_I
- **Discord:** https://discord.gg/MWraGyf

This fork exists strictly because I wanted a few balance knobs turned differently in my own install — it is not a replacement for, or a competing project against, the upstream mod.

## What This Patch Changes

| Spell / Ability | Change | Rationale |
|---|---|---|
| **Greater Heroism** (L5 spell) | HP +25%→+15%, THAC0 60%→85%, Saves +4→+2 | Too large a jump from L2 Heroism; stacked too well with other buffs |
| **Song of Heroism** (HLA) | Temp HP +4/level→+20 flat, AC +6→+4, Saves +6→+4 | Scaling HP was excessive at high levels; combined with Greater Heroism it was overwhelming |
| **Resonating Weapon** (HLA) | Removed stun; retains five rounds of cascading 2d6 damage and the eight-selection limit; corrected bundled 6d2 dice | Repeated overlapping stun checks could lock down groups; cascading party damage is already a strong HLA |
| **Hymn of Requiem** (HLA) | Flat 60→6d10 damage/heal, Save vs. Spell for half; corrected the damage flag that previously selected reverse HP drain | Flat unmitigated damage felt out of place; dice rolls add variance and counterplay |
| **Legionnaire's March** (HLA) | Base THAC0 0→+3 to hit; duration 1 turn→3 rounds; retains +4 damage, non-warrior fighter APR progression and three selections | Bounds the accuracy bonus instead of granting the whole party endgame fighter accuracy |
| **Song of Freedom** (HLA) | Removed 1-turn immunity, kept AoE cleanse | The AoE dispel is already a strong HLA; blanket immunity on top was redundant |
| **Warsong of the Undying** (Skald HLA) | Singer and allies gain +5 AC and +15% to all resistances; allies gain +3 to hit and damage. Haste and immunities unchanged. | Keeps the enhanced song's defensive benefits without increasing the level-20 song's attack and damage bonuses |
| **Symphony of the Dark Children** (Abettor HLA) | Removed the +6 Luck/damage-luck, extra AC/vs.-Good, backstab-immunity, random-invisibility, and Time Stop package; reduced total save bonus from +5 to +1; intended one-round party Invisibility at song start/end | Keeps the core shadow-song identity without the unrelated singer-only power stack; start/end party Invisibility remains a [known issue](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/5) |
| **Dancer** (component 1005) | Halved passive and song AC bonuses, rounding passive totals down; normal song AC +1/+2/+3/+4/+5; Swift-As-Flowing-Water AC +20→+10 and hit/damage +8→+5 | Reduces defense across the kit and keeps enhanced song hit/damage at the normal level-21 value |
| **Piercing Mockery** (Jester song, component `1002`) | AC penalties at levels 1/10/15/20: -2/-2/-3/-4; miscast chances: 12/20/27/27% | Keeps the base AC penalty and halves later scaling; halves miscast chances, rounding down to whole percentages |
| **The Fool's Journey** (Jester HLA) | Enemy AC penalty -6, miscast 35%, critical miss modifier +3; singer AC bonus +5, +10 total against ranged attacks | Reduces the enhanced song's debuffs and personal defense; enemies still cannot critically hit |
| **Heckle** (Jester) | Critical miss modifier +3, spell failure 40%, berserk for 1 round; blockable by level-based spell protections | Gives spell protections counterplay and reduces the taunt's strength and berserk duration |
| **Mad Ramble** (Jester) | Daily uses gained at levels 11/15/19 | Delays access and subsequent uses |
| **Thunderclap** (Storm Drummer) | Stun 1 turn→1 round; deafness/miscast lasts 2 rounds at 25% spell failure; keeps save -4 and friendly fire | A level-10 ability should not disable an encounter for ten rounds |
| **Millenia of Deathly Stillness** (Darkbloom HLA) | Enemy Magic Resistance set to 0→reduced by 50 percentage points; ally arcane caster-level bonus +6→+3 and casting-speed bonus +2→+1 | Preserves the spell-support role without erasing arbitrary amounts of enemy Magic Resistance |
| **Dark Entanglement / acid backstab** (Darkbloom) | Poison chance 100%→10%, duration 12→5 seconds; acid damage 8d2→2d8 | Makes the resources match their existing descriptions |
| **Die Aufklärung** (Kapellmeister HLA) | Casting speed +2→+1, singer MR +50%→+25%, spell saves +10→+5; correct singer/recipient refresh; retains +4 INT/caster levels | Reduces stacked support and defense while preventing overlapping pulses from duplicating bonuses |
| **Checkmate** (Strategist) | Intelligence-based save penalty capped at -3; stun 1 round, Improved Haste 2 rounds | Limits the combination of strong area control and doubled party attack rate; retains the Intelligence condition and level-20 daily use |

The [Bard balance audit](docs/bard-balance-audit.md) records the review scope,
remaining candidates, and focused live-playtest checks. These changes have
automated resource/installer coverage. The user reported successful Bard kit,
shared-ability and Abettor playtesting on 16 September 2026 and approved release.
That broad playtest does not separately establish the opening/finale party
invisibility tracked in issue #5. The Darkbloom Spell Revisions exclusion still applies.

## Installation

Version **v2.9c-balance.6** adds optional component **3010 — Kit-specific bard
spell progression** using the EEex-based progression provider from
[chriz-bg-rebalance v0.5.0](https://github.com/Chrizhermann/chriz-bg-rebalance/releases/tag/v0.5.0).
Install its
component **420** (provider), then install this component after the desired
Bardic Wonders kits and description-changing tweaks. For the collection's
complete Bard policy, use **420 → 421 → 3010**. Standalone users can use
**420 → 3010** and retain their chosen progression for ordinary Bards and
native Bard kits; component **421** is optional.
This requires the provider's supported Windows game/EEex build; it is not a
standalone replacement for EEex and has no non-EEex fallback.

| Bardic Wonders kit | Base spell progression |
|---|---|
| Dancer | Original Baldur's Gate curve, through spell level 6 |
| Kapellmeister, Darkbloom | Icewind Dale curve, through spell level 8 |
| Abettor, Storm Drummer, Troubadour, Deathsinger, Strategist | Icewind Dale curve, through spell level 7 |

Optional base policy **421** gives Blade and Skald the original curve through spell level 6,
and the ordinary Bard and Jester the Icewind Dale curve through spell level 7.
The Icewind Dale curve unlocks spell level 7 at Bard level 21 and spell level 8
at Bard level 29. Existing kit modifiers remain: Dancer's spell-slot penalty,
Kapellmeister's two bonus slots, Darkbloom's bonus slot, and Skald's early
casting delay and caster-level penalty. Special abilities such as Kapellmeister's
Song of Universal Harmony retain their separate spell access.

Component 3010 registers only installed, supported kits and updates their
in-game descriptions. Native-kit description notes are refreshed only when
their registered progression matches that note. It does not change Mage/Bard
multiclasses or Gallant.
The shared engine hook is supplied once by chriz-bg-rebalance, rather than copied
into this fork. **Darkbloom is optional:** when absent, it is skipped; when
installed, it receives the eighth-level progression and keeps its existing
bonus spell slot. Its presence does not change the other kits' mappings.
The progression component imposes no Spell Revisions restriction. The separate
Darkbloom warning above concerns its imported spells, which this component does
not repair; it does not prevent using the progression component without
Darkbloom. The user reported a successful BG2:EE/EET 2.7.3 live smoke test on
20 September 2026. IWDEE 2.7.3 support has executable and installer verification;
an IWDEE in-game check remains. These checks do not independently verify
Darkbloom's imported spell behavior.

See the [v2.9c-balance.6 release notes](docs/releases/v2.9c-balance.6.md) for
installation and verification details.

For a fresh or future installation, use this fork as the Bardic Wonders mod and
select the desired kit components. Shared HLA changes require **High Level
Abilities** (component `2007`). For Abettor's Symphony, install both **Abettor of
Mask Kit** (component `1004`) and **Bard Song Mechanics Tweak** (component `2004`).
Symphony is exposed only after component `2004` validates and patches the
finite-song controller. Version **v2.9c-balance.5** incorporates the pending
component-2004 compatibility fix and the **1.1.0** Abettor tail: generated payload
names, registered projectiles and allocated feedback strings are recognized;
existing song refresh effects are preserved. The tail also restores a Symphony
HLA row omitted by an earlier skipped validation.

See the [component-2004 compatibility report](docs/abettor-component-2004-compatibility.md)
for the root cause and preserved-resource checks.

For an existing, already-stacked playthrough, do not reinstall older WeiDU
components merely to pick up this change. Use the narrowly scoped tail component
under [`live-patch/abettor-hla`](live-patch/abettor-hla) at the end of the current
install order and follow its safety instructions. That tail component applies
only the Abettor rebalance; it does not deliver the other kits' changes in this
release.

### Deferred compatibility fixes

Phase 0 documents the exclusion without changing installer or spell code. The
later compatibility implementation must:

- resolve Darkbloom's intended spells semantically and validate a bundled
  fallback instead of assuming fixed `SPPRxxx` slots;
- audit the other priest-spell clones in New Bard Spells, Troubadour, and
  Deathsinger under both vanilla and Spell Revisions;
- make New Bard Spells/Gallant integration independent of component order; and
- add install-and-uninstall fixtures that verify spell identity, mechanics,
  type, level, and class availability before the warning is removed.

## Acknowledgments

- **Argent77** — `a7#add_kit_ex.tpa` library used by the original mod.
