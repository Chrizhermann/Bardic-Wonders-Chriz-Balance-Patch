# Bardic Wonders — Balance Patch

A balance patch for [Bardic Wonders](https://github.com/TheArtisanBG/Bardic-Wonders) by [The Artisan](https://artisans-corner.com/bardic-wonders/), a fantastic mod that overhauls and expands the Bard class for BG:EE, BG2:EE, EET, and IWD:EE.

All credit for the original mod — the kit designs, spells, items, and overall vision — goes to The Artisan. This fork only adjusts numbers for personal balance preferences while keeping the spirit of each ability intact.

## What This Patch Changes

| Spell / Ability | Change | Rationale |
|---|---|---|
| **Greater Heroism** (L5 spell) | HP +25%→+15%, THAC0 60%→85%, Saves +4→+2 | Too large a jump from L2 Heroism; stacked too well with other buffs |
| **Song of Heroism** (HLA) | Temp HP +4/level→+20 flat, AC +6→+4, Saves +6→+4 | Scaling HP was excessive at high levels; combined with Greater Heroism it was overwhelming |
| **Resonating Weapon** (HLA) | Stun 20%→10%, Save penalty -5→-2, Uses 16→8 | Party-wide stun-lock with cascading AoE was too dominant |
| **Hymn of Requiem** (HLA) | Flat 60→6d10 damage/heal, Save vs. Spell for half | Flat unmitigated damage felt out of place; dice rolls add variance and counterplay |
| **Song of Freedom** (HLA) | Removed 1-turn immunity, kept AoE cleanse | The AoE dispel is already a strong HLA; blanket immunity on top was redundant |

**Legionnaire's March** is on the list but still being evaluated.

## Installation

Install [Bardic Wonders](https://github.com/TheArtisanBG/Bardic-Wonders) first, then install this patch over it. Standard WeiDU installation.

## Acknowledgments

- **The Artisan** — original mod author. The kit concepts, spell design, and creative direction are all theirs.
- **Argent77** — `a7#add_kit_ex.tpa` library used by the original mod.
