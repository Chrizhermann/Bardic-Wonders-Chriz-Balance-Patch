# Priest-spell copies and the Gallant integration — 14 October 2026

This records the fixes for issues #2, #3 and #4. They are on the development
branch and not yet released. The Darkbloom Spell Revisions exclusion in the
README stays in force until they are released and checked in a Spell Revisions
game.

## What was wrong

Darkbloom (1006), Troubadour (1008), Deathsinger (1009) and New Bard Spells
(2008) copy priest spells into private wizard spells. They copied fixed
physical files (`SPPR112.SPL` and so on). Spell Revisions, IWDification and
IWD:EE keep spells in other files, so a fixed name can copy an unrelated spell.
In two inspected installations with Spell Revisions and IWDification, the
files Darkbloom used hold Strength of Stone, Cause Moderate Wounds, Icelance,
Smashing Wave and Destruction. When the file was missing, Darkbloom installed
its bundled IWD spell together with icons, an item, projectiles and visual
effects under their original names, which other mods may own.

Every copy also kept its source's identity effects. Opcodes 206, 318, 321 and
324 name a spell by resref; a copy that only names its source does not refresh
or block itself, so a recast could stack with the earlier cast (Aid under
Spell Revisions, Doom and Defensive Harmony also in vanilla BG2:EE).

New Bard Spells gave the Gallant its spells only when the Gallant kit (1012)
was already installed. Installing 1012 after New Bard Spells left the kit
without them and its `<BARDIC_SPELLS>` placeholder unfilled.

## Behavior now

- Each copy names its spell by `SPELL.IDS` symbol and copies the file that
  symbol points to. A symbol that is missing, outside the priest range, or
  points to a missing or malformed SPL stops the component with a message.
- The copy gets the bard type (wizard) and the listed level. Mechanics and
  every other header field come from the installed spell.
- Identity effects naming the source gain a twin naming the copy, placed
  before it. The copy refreshes and blocks itself like its source, and still
  ends the source's effects as before. The installed source is not modified,
  so a later cast of the source does not end the copy's effects.
- Mold Touch's opcode 78 applies `<parent>B` when its resource is empty, so a
  renamed copy looks for a sub-spell that does not exist (the old Darkbloom
  fallback looked for `C0BDDS3B` but installed `SPPR326B`). Copies now name
  the sub-spell explicitly.
- Darkbloom alone has bundled fallbacks. When the installation lacks Curse,
  Beast Claw, Mold Touch, Thorn Spray or Mist of Eldath, the bundled IWD spell
  and its icons, Beast Claw weapon, projectiles, visual effects and Mold Touch
  sub-spell are installed under `C0BDD*` names. Projectiles are registered
  under new names, and references between these bundled resources use the new
  names. No installed file is replaced. The bundled Mold Touch now also gets
  the wizard type and level 3; the old code left it a priest spell and wrote
  those values to its sub-spell.
- Whichever of New Bard Spells and the Gallant kit is installed second runs
  the Gallant integration (`lib/gallant_new_spells.tpa`). It is idempotent, and
  each component's WeiDU backup undoes its part.

## Copies and availability

Type is 1 (wizard) for every copy. Darkbloom, Troubadour and Deathsinger grant
copies through their kit tables at the listed character level; New Bard Spells
adds its copies to the bard spell list with the listed scroll.

| Component | Copy | Symbol | Level | Grant | Vanilla BG2:EE source | SR + IWDification source |
|---|---|---|---:|---|---|---|
| Darkbloom | `C0BDDS1` | `CLERIC_CURSE` | 1 | kit, 2 | bundled fallback | `SPPR121` Curse |
| Darkbloom | `C0BDDS2` | `CLERIC_BEAST_CLAW` | 2 | kit, 4 | bundled fallback | `SPPR222` Beast Claw |
| Darkbloom | `C0BDDS3` | `CLERIC_MOLD_TOUCH` | 3 | kit, 7 | bundled fallback | `SPPR333` Mold Touch |
| Darkbloom | `C0BDDS4` | `CLERIC_THORN_SPRAY` | 4 | kit, 10 | bundled fallback | `SPPR428` Thorn Spray |
| Darkbloom | `C0BDDS5` | `CLERIC_INSECT_PLAGUE` | 5 | kit, 13 | `SPPR517` Insect Plague | same |
| Darkbloom | `C0BDDS6` | `CLERIC_FIRE_SEEDS` | 6 | kit, 16 | `SPPR606` Fire Seeds | same |
| Darkbloom | `C0BDDS7` | `CLERIC_MIST_OF_ELDATH` | 7 | kit, 30 | bundled fallback | `SPPR738` Mist of Eldath |
| Troubadour | `C0TRBS1` | `CLERIC_CURE_LIGHT_WOUNDS` | 1 | kit, 2 | `SPPR103` Cure Light Wounds | same |
| Troubadour | `C0TRBS2` | `CLERIC_AID` | 2 | kit, 4 | `SPPR201` Aid | same (self-refreshing) |
| Troubadour | `C0TRBS3` | `CLERIC_CURE_MEDIUM_WOUNDS` | 3 | kit, 7 | `SPPR315` Cure Medium Wounds | `SPPR315` Cure Serious Wounds |
| Troubadour | `C0TRBS4` | `CLERIC_CURE_SERIOUS_WOUNDS` | 4 | kit, 10 | `SPPR401` Cure Serious Wounds | `SPPR401` Cure Critical Wounds |
| Troubadour | `C0TRBS5` | `CLERIC_MASS_CURE` | 5 | kit, 13 | `SPPR514` Mass Cure | same |
| Troubadour | `C0TRBS6` | `CLERIC_HEAL` | 6 | kit, 16 | `SPPR607` Heal | same |
| Deathsinger | `C0DESP1` | `CLERIC_DOOM` | 1 | kit, 2 | `SPPR113` Doom (self-refreshing) | same |
| Deathsinger | `C0DESP4` | `CLERIC_CLOAK_OF_FEAR` | 4 | kit, 10 | `SPPR416` Cloak of Fear | same |
| Deathsinger | `C0DESP5` | `CLERIC_SLAY_LIVING` | 5 | kit, 13 | `SPPR511` Slay Living | same |
| New Bard Spells | `C0BW303` | `CLERIC_REMOVE_PARALYSIS` | 3 | `SPPR308C` | `SPPR308` Remove Paralysis | same |
| New Bard Spells | `C0BW401` | `CLERIC_FREE_ACTION` | 4 | `SCRL58` | `SPPR403` Free Action | same |
| New Bard Spells | `C0BW402` | `CLERIC_DEFENSIVE_HARMONY` | 4 | `SCRL59` | `SPPR406` Defensive Harmony (self-refreshing) | same |
| New Bard Spells | `C0BW501` | `CLERIC_CHAOTIC_COMMANDS` | 5 | `SCRL5F` | `SPPR508` Chaotic Commands | same |
| New Bard Spells | `C0BW602` | `CLERIC_WONDROUS_RECALL` | 6 | `C0BW602A` | `SPPR611` Wondrous Recall | same |

The sources were read from an unmodified BG2:EE resource set and from two
installations with Spell Revisions and IWDification. In both installations,
`SPPR738` is named "Healing Mist"; its effects and description text are those
of Mist of Eldath. The `SPELL.IDS` that SCS ships for IWD:EE maps these symbols
to IWD:EE's own files (Curse is `SPPR112` there), so the copies follow them;
no IWD:EE installation was checked.

## Tests

From the repository root:

```powershell
python -B -m unittest tests.test_priest_spell_imports tests.test_darkbloom_spell_imports tests.test_gallant_new_spells -v
python -B -m unittest discover -s tests -t . -v
python -B -m tools.verify_installers
```

The tests run the production WeiDU code with the bundled WeiDU on synthetic,
empty-key games. They cover vanilla, Spell Revisions-like (renamed cures,
self-references, unrelated spells in Darkbloom's old files), IWD-like and
mixed layouts; spell name, mechanics, type, level and kit availability;
byte-exact fallbacks; failures that roll back; reinstall; byte-exact uninstall;
both Gallant install orders with each component reinstalled or removed; and
unchanged unrelated tables and kit rows. They do not run the game.

## Open question

Under Spell Revisions, `CLERIC_CURE_MEDIUM_WOUNDS` and
`CLERIC_CURE_SERIOUS_WOUNDS` are named Cure Serious Wounds and Cure Critical
Wounds. The Troubadour therefore gets those spells at levels 3 and 4, while
the kit description lists Cure Medium Wounds and Cure Serious Wounds.
Likewise, Darkbloom's seventh-level copy is named Healing Mist in the two
inspected installations, while its kit description lists Mist of Eldath.
Options: fill the descriptions' spell names from the installed spells, describe
the grants generically, or leave the text as is.

## Not changed

- In-game behavior is unverified, including a Spell Revisions game.
- Gallant copies (`C0GA*`) still name the bard spells in their identity
  effects, as the Heroism handoff also notes for `C0GA202` and `C0GA502`, so
  a Gallant's recast can stack with its earlier cast. Battleluck's Gallant copy
  already refreshes itself.
- Inspirations (2002) and High Level Abilities (2007) still adjust the Gallant
  only when the kit is installed first.
- Darkbloom's bundled Beast Claw and Mist of Eldath refer to visual resources
  (`ALTERH`, `MOELDAA`) that are not bundled; where a game lacks them, only
  the visual is missing.
