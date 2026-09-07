# Component 2004 compatibility skip: CEBG Alpha13

## Status and evidence

Fixed in the development worktree; not yet released. The completed
`Alpha13-20260907` installation remained read-only. No game or full-stack
installation was run. This is installer/resource validation, not in-engine
acceptance of the separate Symphony invisibility issue #5.

The authoritative attempt-owned log is
`.chriz/attempts/attempt-7da66eb7040f78cca7c1/steps/0091-c73ec1a85870a6db/attempt-0001/stdout.log`:
warning at line 4573; installed-with-warnings at line 4621. Its SHA256 is
`eb3d40b1bcd3d4a77e775dfd8d829fb82d0f595e4aaddc6aa45ef01c34c908d5`.
The overwritten root `SETUP-BARDICWONDERS.DEBUG` is not evidence for this failure.

## Exact mismatch

The first failing gate in `v2.9c-balance.3` was
`FILE_EXISTS_IN_GAME ~C0ABETS2.EFF~`. Component 2004 does not create that
resource. It creates a dynamically named same-base SPL/EFF pair, referenced
directly by `C0ABETS2.SPL`; this installation allocated `C0BW0001`.
The missing-file gate prevented the later validators from running. Comparing
their predicates with the actual producer also exposed three latent failures:

| Predicate in balance.3 | Actual producer output in Alpha13 |
| --- | --- |
| Controller ability projectile equals 1 | 444; `PROJECTL.IDS` contains `443 c0bardso`, and the SPL field uses ID + 1 |
| Ability opcode 146 / `C0BARDSX` parameter2 equals 1 | 0; the separate global opcode 146 correctly remains 1 |
| `C0SINGIN.SPL` opcode 139 parameter1 equals 0 | Allocated TLK strref 224503, "Singing Bard Song" |

All four mismatches are between Bardic Wonders' own producer and validator.
There is no evidence attributing this skip to Spell Revisions.

## Provenance

The controller, dynamic payload pair, and singing hooks originate from Bardic
Wonders component 2004. The Abettor payload donor and HLA originate from
component 1004. Current controller/hook bytes match the component-2004 producer
exactly after its resource-name, projectile, and feedback-strref substitutions.

Component 2006 is the sole later owner modifying the dynamic payload: it adds
one opcode 326 `C0BSNGEF` visual effect. Its backup preserves the exact post-2004
payload. All `MAPPINGS.*`/`UNINSTALL.*` ownership records were checked for these
resources; no other later owner was found.

| Captured resource, relative to `game/` | SHA256 |
| --- | --- |
| `override/C0ABETS2.SPL` | `4cea194a6bb32c07985af740ea3b0b5628ba7865e6f643958f2e61828103120d` |
| `override/C0BW0001.EFF` | `c8c80e4fa2448df132e0333bd623c1763ee43cbae2a11ddebb41daea49dfc770` |
| `override/C0SINGIN.SPL` | `814bfa56c30b77e894efb17ed446676bfedc5c4c36f9309072e1e9e599d1a558` |
| `weidu_external/backup/BardicWonders/2006/C0BW0001.SPL` | `63887cb0e4d0bbb7442dbffe5175e727cb5ede2e5ec03518f2662b74006dc185` |

## Repair and regression

- Resolve exactly one well-formed, nonreserved payload candidate per controller
  ability, requiring agreement across every ability. Validate its actual EFF/SPL
  and the complete controller before adding the HLA.
- Require the projectile allocated by the actual producer. The standalone tail
  patch independently resolves `C0BARDSO` through `PROJECTL.IDS` (+1).
- Match the shipped per-ability casting mode, while retaining the distinct
  global casting-mode check. Allow an allocated nonnegative feedback strref only
  on opcode 139, which is removed when constructing the invisibility spell.
- Keep strict durations, timing, effect fields, reserved-resource checks,
  post-patch verification, and failure/rollback behavior. Add validation-stage
  diagnostics. Overflow-safe bounds checks reject malformed controller offsets.
- Correct synthetic fixtures so they no longer invent `C0ABETS2.EFF` or default
  to the wrong projectile/casting-mode/string fields.

The real-producer regression executes unchanged `bardsongtweaks.tpa` against
bundled resources in temporary fake games, with two different projectile and
payload allocations. It reproduces the released failure and passes with the
fix. It checks all 11 headers, original global and per-header effect bytes,
finite durations 600 through 1600 ticks, cooldown resources, one opening/finale
pair per header, party projectile 158, and one HLA entry.

A separate replay copied the completed installation's controller, hooks,
HLA/table, and EFF plus component 2006's payload backup into two isolated
fixtures. The released library returned exit 3 and the exact skip warning;
the fixed library returned exit 0 with 11 opening hooks, 11 finale hooks, and
one HLA entry. Every original controller effect and payload byte was preserved.
All eight source-file hashes were unchanged before and after replay.

Run the repository suite from its root:

```powershell
python -B -m unittest discover -s tests -t . -v
```

Result on 2026-09-07: **95 tests passed** (20.233 seconds), including the
standalone tail patch's reversible install/uninstall and malformed-input cases.

## Release and collection pin requirements

1. Merge the validated fix and publish a new immutable release, proposed
   `v2.9c-balance.4`; do not replace or move the existing balance.3 tag/artifact.
2. Synchronize the primary TP2 version and release tag. If the separately
   distributed tail patch is published, bump its own TP2 version too.
3. Update CEBG's authoritative Bardic Wonders source pin to the new release
   (or explicitly chosen immutable commit), archive URL, and freshly verified
   archive SHA256. Regenerate affected lock/bundle metadata and verify the
   packaged `abettor_hla_finite.tpa` comes from that revision.
4. Retain components 1004 and 2004 for Symphony. A fresh installation using the
   fixed main mod does not need the legacy tail repair layered over it.
   The legacy tail patch does not restore a missing HLA availability row, so its
   validator alignment is not a complete repair plan for the skipped Alpha13 HLA.
5. Keep completed Alpha13 unchanged. Use a future separately authorized build
   to confirm the installation warning is gone; test start/end party
   invisibility in-engine separately before closing issue #5.
