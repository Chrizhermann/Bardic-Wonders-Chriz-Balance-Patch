# Bard spell and Blade follow-up — 11 October 2026

This follow-up starts from `v2.9c-balance.6`, commit
`7db986160fcc5f466ecb8730eabd6bb226ee71c2`. Upstream master remains
`4e72d9739d6728d688484618281ed6c3a7428b4c` and is already an ancestor of the
fork. No upstream merge is required.

## Spell-level ceilings: completed and released

Christopher clarified that "finish the bard rebalance" refers to different
spell-level ceilings for the kits. It does not authorize the old song, spin,
parry or spell-import backlog. That ceiling policy is already implemented in
released Bardic Wonders balance.6 and chriz-bg-rebalance v0.5.0 or later:

| Kits | Normal spellbook ceiling |
|---|---:|
| Blade, Skald, Dancer | 6 |
| Bard, Jester, Abettor, Storm Drummer, Troubadour, Deathsinger, Strategist | 7 |
| Kapellmeister, Darkbloom | 8 |

The complete collection policy is provider **420 → base policy 421 → Bardic
adapter 3010**, after the desired kits and description tweaks. Without 421,
3010 deliberately leaves native Bard/Blade/Skald/Jester registrations alone.
Seventh-level spells unlock at Bard level 21, eighth-level spells at level 29;
existing slot bonuses and penalties remain. Separate special-ability spell
access is unchanged. See the [release notes](releases/v2.9c-balance.6.md).

No ceiling source change is needed. Installation presence in Garithos is being
checked by the collection chat; this work does not inspect or modify that game.
Heroism, Blade proficiency and Battleluck are separate approved follow-ups.

## Settled follow-up changes

Blade may specialize, with two proficiency slots, in bastard swords, long
swords, short swords, two-handed swords, katanas, scimitars/wakizashis/ninjatos,
daggers, axes, spears and halberds. Its automatic Two-Weapon Style grants may
not exceed three slots. These changes do not retrain existing characters,
increase the proficiency budget, alter APR tables, or redesign the spins.

Battleluck becomes a five-round, caster-centered buff for allies within a
30-foot radius, including the caster. Retain its critical-hit modifier of one,
or two from caster level 14, and protection from critical misses. Its ordinary
and Gallant versions must refresh one another instead of accumulating bonuses.
The icon and expiration cue must end with the combat benefits.

General Bard access to Free Action and Chaotic Commands is retained.

## Heroism: approved policy, pending shared integration

The requested family contains ordinary Heroism, Greater Heroism, their Gallant
copies, and Potion of Heroism. Song of Heroism and Aid are excluded. Heroism
durations and strengths have not received another numerical change.

Currently, `C0BW202` and `C0BW502` remove both ordinary spell sources before
applying their effects. Gallant copies `C0GA202` and `C0GA502` inherit that
ordinary-only removal list. Neither direction of spell/potion exclusion is
implemented. Do not describe the requested family as working already.

Removing and reapplying an HP modifier can grant additional current HP. The
separate potion-uniqueness research contains native-function counterexamples;
its replacement original-effect admission prototype is not an installable,
released dependency. This follow-up must not silently import that prototype or
append potion removal effects to the spells.

Christopher approved **first-active-wins** in the collection chat on October 11.
An active Heroism, Greater Heroism or Potion of Heroism prevents subsequent
family buffs from adding bonuses, refreshing the duration or upgrading the
active buff. This is no longer awaiting a gameplay decision.

The approved policy still needs a verified implementation: source immunity blocks every
effect from a source, which can suppress unrelated effects added by other mods.
Direct potion effects, Item Revisions linked spell delivery, SCS aliases,
dispelling, existing source protections and install order must be accounted for.

For the direct potion, HP and THAC0 use different effect targets/delivery
paths. Placing a self-immunity last in the file does not prove it arrives after
every first-dose bonus. Existing saves also retain older effects without newly
added guards. These are reasons to verify the admission design, not to require
an exact reference-install layout.

The current potion prototype has no ordinary-spell registration interface and
requires each invocation to target its drinker. Its linked child-spell support
only recognizes proven potion casts. Adding Bardic spell names to its manifest
does not supply normal spell-cast or per-recipient tracking. The existing
Heroism removal effects also need explicit treatment before admission can
preserve the first buff. The [integration handoff](heroism-family-integration.md)
records the exact remaining work. No Heroism gameplay resources were changed.

## Comparison with the original Blade

The original Blade's weapon limit is one slot, with permission to spend three
slots in Two-Weapon Style. This version's two weapon slots and three free style
slots therefore still exceed vanilla weapon training. Charisma-based melee
accuracy also remains. Both versions halve Lore and Pick Pockets.

The Bardic Wonders song trades vanilla luck/fear protection for allied hit
chance and enemy morale penalties. Its Offensive Spin lacks the original
explicit +2 hit/damage bonuses, prevents casting, and initially imposes three
rounds of exhaustion; Improved Offensive Spin later removes that exhaustion.
Defensive Spin has its own protection/counterattack tradeoffs, whose previously
recorded engine concerns are outside this proficiency change.

Sources: [Beamdog Adventurer's Guide, page 25](https://files.beamdog.com/files/BGEE-AdventurersGuide_en.pdf#page=25),
[WEAPPROF table](https://gibberlings3.github.io/iesdp/files/2da/2da_bgee/weapprof.htm),
and this repository's `lib/blade.tpa` and bundled spell resources.

## Validation boundary

All **148 automated tests** pass, including eight new Blade and four new
Battleluck test methods. WeiDU 249 passes **48 installer syntax/version checks**.
Independent review found no blocking issues in these two changes, and the
whitespace/cleanup checks pass. No release or live-game action was performed.

Validation uses disposable resource fixtures and the bundled WeiDU executable.
It does not install into a game, edit a save, or establish live acceptance.
The earlier September playtest applies to the released balance changes, not
these new proficiency and Battleluck changes. The existing Darkbloom/SR and
Symphony-invisibility limitations remain unchanged.

The new fixtures cover the shipped resources, additional/reordered effects and
abilities, alternative proficiency row/column orders, legacy AXE/SPEAR labels,
unrelated-data preservation, repeated application, reinstall/uninstall, and
malformed or missing-target rollback. The changed resource actions do not
read SR priest-spell donors. This does not close the separate Gallant component
order issue or prove an entire modded installation.

A later disposable-game check should confirm:

1. Blade can spend at most two points in each listed weapon group and receives
   three Two-Weapon Style points at levels 1, 12 and 16.
2. Battleluck affects the caster and allies inside 30 feet, excluding enemies
   and allies outside the area; its bonuses and icon expire after five rounds.
3. A second Battleluck refreshes duration without increasing the critical
   bonus, including casts from a different caster or the Gallant version.
4. Battleluck still grants its stronger critical bonus at caster level 14.
