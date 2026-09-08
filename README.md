# Bardic Wonders — Balance Patch

A personal balance-patch fork of [Bardic Wonders](https://github.com/TheArtisanBG/Bardic-Wonders) by **Artemius_I** (also known as **The Artisan** / **AionZ**), a fantastic mod that overhauls and expands the Bard class for BG:EE, BG2:EE, EET, and IWD:EE. All kit concepts, spell design, items, and creative direction are the original author's work; this fork only adjusts numbers for personal balance preferences while keeping the spirit of each ability intact.

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
| **Resonating Weapon** (HLA) | Stun 20%→10%, Save penalty -5→-2, Uses 16→8 | Party-wide stun-lock with cascading AoE was too dominant |
| **Hymn of Requiem** (HLA) | Flat 60→6d10 damage/heal, Save vs. Spell for half | Flat unmitigated damage felt out of place; dice rolls add variance and counterplay |
| **Song of Freedom** (HLA) | Removed 1-turn immunity, kept AoE cleanse | The AoE dispel is already a strong HLA; blanket immunity on top was redundant |
| **Warsong of the Undying** (Skald HLA) | Singer and allies gain +5 AC and +15% to all resistances; allies gain +3 to hit and damage. Haste and immunities unchanged. | Keeps the enhanced song's defensive benefits without increasing the level-20 song's attack and damage bonuses |
| **Symphony of the Dark Children** (Abettor HLA) | Removed the +6 Luck/damage-luck, extra AC/vs.-Good, backstab-immunity, random-invisibility, and Time Stop package; reduced total save bonus from +5 to +1; intended one-round party Invisibility at song start/end | Keeps the core shadow-song identity without the unrelated singer-only power stack; start/end party Invisibility remains a [known issue](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/5) |

**Legionnaire's March** is on the list but still being evaluated.

## Installation

For a fresh or future installation, use this fork as the Bardic Wonders mod and
install both **Abettor of Mask Kit** (component `1004`) and **Bard Song Mechanics
Tweak** (component `2004`). Symphony is exposed only after component `2004`
validates and patches the finite-song controller.

For an existing, already-stacked playthrough, do not reinstall older WeiDU
components merely to pick up this change. Use the narrowly scoped tail component
under [`live-patch/abettor-hla`](live-patch/abettor-hla) at the end of the current
install order and follow its safety instructions.

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
