# Abettor HLA finite-song rebalance

This is a one-component WeiDU tail patch for an existing Bardic Wonders playthrough. It rebalances **Symphony of the Dark Children** and adds one round of ordinary party Invisibility when the finite song begins and again when it ends.

> [!NOTE]
> The broader kit is accepted for release based on earlier live-install work,
> but the new party Invisibility at song start/end has no surviving in-engine
> verification and may not trigger. This is tracked as [issue
> #5](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/5)
> and does not undo the other balance changes made by this patch.

This legacy tail component updates song resources and the HLA description; it
does not restore a missing `LUC0ABET.2DA` availability row. It is therefore not a
complete repair for a `v2.9c-balance.3` installation that skipped Symphony.
See the [component-2004 compatibility report](../../docs/abettor-component-2004-compatibility.md)
for the future-release path; any existing-stack repair needs a separate plan.

## Safety requirements

- Install it as the **last component** in the WeiDU stack. Do not pop, reinstall, or reorder Bardic Wonders, Safana, SCS, or another existing component.
- Before installation, confirm the exact game directory. Multiple modded BG2EE installs may exist; never infer the target from a similar folder name.
- Fully close `Baldur.exe` and `InfinityLoader.exe` before installation or uninstall. A locked `dialog.tlk` can leave invalid strings.
- The patch requires the recognized finite-duration component-2004 controller. It deliberately fails without that controller; there is no toggle-song fallback.
- The payload is resolved from the controller, and its projectile must match the installed `C0BARDSO` entry in `PROJECTL.IDS`. No `C0ABETS2.EFF` pointer is required.

Copy `Setup-AbettorHLARebalance.tp2` and the `abettor-hla-rebalance` directory to the confirmed game directory. Place a current WeiDU executable beside them as `Setup-AbettorHLARebalance.exe`, then run it and install component 0.

## Uninstall

Run `Setup-AbettorHLARebalance.exe` again and choose uninstall for component 0. WeiDU restores the exact backed-up resources, their original string references, every pre-existing TLK entry, and the prior active component order. WeiDU keeps the two newly allocated name/description strings as unreferenced, append-only TLK entries; reinstalling the same text reuses them rather than growing the TLK again. Older components must remain in their existing order.

After installing or uninstalling, fully restart the game. Let any already-active song effects expire before testing a fresh Bard Song activation.

## Disposable verification

Never point the verifier at a game install. Build a new isolated copy in an empty directory outside the source game tree, then verify only that generated copy:

```powershell
python -m tests.abettor_hla.make_fixture --source "<confirmed-read-only-game-copy-source>" --destination "<new-empty-disposable-directory>"
python -m tests.abettor_hla.verify_fixture --fixture "<new-empty-disposable-directory>"
```

The builder refuses reserved-resource collisions and destinations inside the source tree. It copies `PROJECTL.IDS` and generates an empty synthetic KEY so WeiDU can resolve installed projectile IDs; it never copies the game's KEY or BIFs. The verifier requires its generated sentinel, manifest hashes, and exact synthetic KEY bytes, rejects game executables, installs and uninstalls only in the disposable directory, and prints `DISPOSABLE_FIXTURE_VERIFICATION=PASS` only after the semantic contract, exact resource restoration, pre-existing TLK entries, and active component order all pass.
