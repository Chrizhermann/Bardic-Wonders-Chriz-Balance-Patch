# Heroism family integration — October 11, 2026

## Approved behavior

Christopher approved first-active-buff behavior in the collection chat. The
family consists of Heroism, Greater Heroism, their Gallant aliases, and Potion
of Heroism. The first active buff keeps its original benefits and expiration.
Later family applications add no family bonuses, do not refresh its expiration,
and do not replace it with a stronger tier. Different recipients are independent.

Song of Heroism, Aid and Potion of Power are outside this family. Proven copies
of Potion of Heroism follow its identity; a similar HP effect or English name
alone does not prove membership. Preserve normal charge/spell consumption,
casting, native immunity and dispelling, and unrelated effects added by mods.
Unrelated instant healing, cures, permanent effects and penalties still follow
their original behavior when a repeated Heroism bonus is rejected.

The first application is not removed and re-created. This matters for HP:
removal/reapplication can heal wounds. Normal expiry or legitimate native
removal allows another family application. Cosmetic records alone must not
keep the family blocked after its gameplay bonuses are gone.

## Current source state

This is an implementation handoff, not an installed or working exclusion patch.
The rule no longer needs a user decision. Heroism resource behavior remains
unchanged while its shared implementation is incomplete.

| Source | Current behavior |
|---|---|
| `C0BW202.SPL`, `C0BW502.SPL` | Leading opcode321 effects remove both ordinary spell sources; latest cast replaces them. |
| `C0GA202.SPL`, `C0GA502.SPL` | Gallant copies retain ordinary-only removal names. |
| `POTN09.ITM` | No reciprocal exclusion with Bardic spells. Some overhauls instead deliver its bonuses through a spell. |
| Song/Aid | Outside this change. |

An admission filter that merely rejects the new HP bonus is insufficient:
the preceding opcode321 can still remove the first active buff. Conversely,
removing those controls before the replacement admission path is active would
permit stacking. Keep both changes in one validated integration transaction.

## Verified shared-provider gap

The inspected implementation is the **unpublished** original-effect prototype
under `chriz-bg-rebalance/research/prototypes/potion-admission`. It is not a
released provider dependency or an available normal installer component.

Its `CBRPQCore.lua` already has a first-active HP-family policy which rejects
incoming owned records without rewriting old effects. Its transport and
registration remain potion-specific:

- `CBRPQCompile.lua:609` compiles explicit item inputs. Lines699–703 reject
  owned-family source-removal controls without an adapter.
- `potion_registry.tpa:13` inventories potion-category ITMs, not Bard spells.
- `CBRPQRuntime.lua:69` starts item-use invocations; line78 excludes ordinary
  spell sources. Its admission callback at line179 requires the drinker and
  binds an invocation to one recipient.
- `CBRPQLineage.lua:34` handles child spells only after a proven tracked potion
  carrier. An ordinary cast of the same spell deliberately remains unowned.
- `CBRPQBoot.lua:5` and `CBRPQLab.lua:7` compose one registry before hooks arm.
  There is no external spell-family registration or manifest-merge API.

Adding spell names to that inventory cannot activate the requested behavior.
Copying its hooks into Bardic would duplicate ownership without supplying the
missing spell transport. Do not advertise resource metadata as a working fix.

Whole-resource immunity is also insufficient for the stated preservation rule:
it can block unrelated potion-added records. Direct potion HP and THAC0 may
travel through different paths, so file order alone is not proof that a guard
placed last cannot reject part of the first dose. The existing Item Revisions
child-spell protections and original dispel eligibility must be preserved.

## Concrete remaining implementation

The shared provider must own native effect admission and expose a versioned
registration capability before Bardic enables this policy. Required capabilities:

1. Recognize an ordinary spell-root invocation using actual cast identity,
   including direct, queued and projectile delivery. Track decisions separately
   for each recipient. Do not substitute a timestamp or resource name for a
   unique invocation.
2. Preserve the original source type/name, caster and dispel level, timing,
   probability, saving throws and first-application HP state. Inspect live
   owned bonuses before admitting the next application; never remove/reapply
   HP or refresh its deadline.
3. Join the four Bardic sources with provider-proven Potion of Heroism copies
   in one explicit family. Preserve unrelated potion-family policies.
4. Recognize Bardic's owned refresh controls and suppress them only once the
   replacement first-active admission path is guaranteed. Preserve foreign
   removal effects and other unrelated records.
5. Recognize still-active family bonuses after save/load or dispelling without
   retaining native pointers or using an orphaned immunity marker as evidence.
   Existing overstacked saves require an explicit policy, not silent HP removal.

Bardic then owns the spell-side descriptor/compiler for `C0BW202/502` and
`C0GA202/502`, capability validation, and accurate spell/scroll descriptions.
Resolve effects by semantics across additional/reordered records and supported
linked layouts. Read the effective resources after the relevant spell/potion
overhauls and alias producers. Missing or ambiguous required capabilities must
produce an honest installation result, not silently promise exclusion.

## Acceptance cases

Exercise each first source against every later family source, both same and
different casters; include a stronger second buff. Confirm no new HP, bonus,
duration extension or removal, while unrelated instant and adverse effects
remain native. Verify first-dose sibling effects all arrive, including split
potion delivery and a spell cast on another actor. Different recipients must
remain independent, including one cast affecting multiple recipients.

Also cover native rejection before admission, expiration, partial legitimate
removal, dispelling, saved active bonuses, reordered/additional records,
SR/non-SR and supported potion-overhaul delivery, proven aliases, repeated
installation and rollback. Confirm Song/Aid/Power remain separate. Synthetic
model or resource tests must not be reported as native gameplay acceptance.

No game, save, provider implementation, release or publication was changed by
this handoff. The completed spell-level ceiling policy is separate and does
not depend on the Heroism work or the old song/spin/import backlog.
