# Abettor HLA finite-song rebalance

This is a one-component WeiDU tail patch for an existing Bardic Wonders playthrough. It rebalances **Symphony of the Dark Children** and adds one round of ordinary party Invisibility when the finite song begins and again when it ends.

> [!NOTE]
> The broader kit is accepted for release based on earlier live-install work,
> but the party Invisibility at song start and end has not been verified in
> the engine. Up to version 1.1.0 the ending did not fire when the song ran
> out; version 1.2.0 replaces it. This is tracked as [issue
> #5](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/issues/5)
> and does not undo the other balance changes made by this patch.

Version **1.2.0** (released with v2.9c-balance.8) ends every Symphony activation
with one round of party Invisibility once that activation's song runs out,
rounded up to the next whole second, also while a newer Symphony is playing.
Earlier versions copied the Bard Song Mechanics Tweak's disabled-singer check,
which fires every round while the singer is disabled and never when the song
ends; 1.2.0 neither copies nor needs `C0SINGI2.EFF`. A playthrough with 1.1.0
can reinstall the tail as 1.2.0. Playthroughs whose component 2004 added the
Symphony hooks itself (`v2.9c-balance.5` to `.7`) are still refused because
`C0ABIVI.SPL` and `C0ABIVS.EFF` already exist; there is no repair for them yet.

Version **1.1.0** supports the actual generated finite controller and restores a
missing `LUC0ABET.2DA` Symphony availability row after resource validation. This
repairs installations where earlier versions skipped Symphony. An existing row
is preserved; unrecognized table widths, duplicate rows, and unexpected Symphony
allowance or prerequisite values are rejected with rollback. Existing self-refresh
and later-mod visual effects remain intact. See the [compatibility report](https://github.com/Chrizhermann/Bardic-Wonders-Chriz-Balance-Patch/blob/master/docs/abettor-component-2004-compatibility.md).

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
