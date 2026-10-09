# 1C 7.7 backup privacy/DR runbook

## Scope

This runbook governs backup artifacts produced by the existing local 1C 7.7 backup process.
It does **not** replace or reinterpret the 1C backup mechanism itself.

Owner rule:
- retention: 30 calendar days;
- storage remains in Russia;
- access: only ИП Шатров;
- no cloud, e-mail or messenger transfer without a separate privacy review;
- disaster-recovery copy: separate encrypted removable drive, disconnected between backup cycles.

## Required topology

1. Working 1C database: local workstation in Penza.
2. Local backup directory: on the same workstation.
3. DR backup directory: on a physically separate encrypted removable drive.
4. The removable drive is connected only for the backup/copy/verification cycle and then disconnected.

A same-disk or same-computer copy is not considered sufficient disaster recovery.

## Daily operating procedure

1. Close or quiesce 1C in the manner required by the existing backup procedure.
2. Run the existing 1C backup and produce a new backup artifact in the local backup directory.
3. Verify that the new artifact exists, has non-zero size and has a fresh timestamp.
4. Connect the encrypted removable DR drive.
5. Copy the new backup artifact to the DR backup directory.
6. Verify copied file size matches the source artifact.
7. Remove backup artifacts older than 30 calendar days from:
   - the local backup directory;
   - the DR backup directory.
8. Record the verification result in the local operator log without customer PII.
9. Safely eject and physically disconnect the removable drive.

## Windows PowerShell verification/rotation

Run in PowerShell with paths adjusted to the actual installation.

```powershell
$LocalBackupDir = "D:\1C_Backup"
$DrBackupDir = "E:\1C_DR_Backup"
$RetentionDays = 30

$Cutoff = (Get-Date).AddDays(-$RetentionDays)

# Show artifacts that are outside retention before deletion.
Get-ChildItem -LiteralPath $LocalBackupDir -File |
    Where-Object { $_.LastWriteTime -lt $Cutoff } |
    Sort-Object LastWriteTime |
    Select-Object FullName, Length, LastWriteTime

Get-ChildItem -LiteralPath $DrBackupDir -File |
    Where-Object { $_.LastWriteTime -lt $Cutoff } |
    Sort-Object LastWriteTime |
    Select-Object FullName, Length, LastWriteTime
```

After reviewing the dry-run output, remove only files in the designated backup directories:

```powershell
Get-ChildItem -LiteralPath $LocalBackupDir -File |
    Where-Object { $_.LastWriteTime -lt $Cutoff } |
    Remove-Item -Force

Get-ChildItem -LiteralPath $DrBackupDir -File |
    Where-Object { $_.LastWriteTime -lt $Cutoff } |
    Remove-Item -Force
```

Verify no artifact older than the retention boundary remains:

```powershell
$LocalExpired = @(
    Get-ChildItem -LiteralPath $LocalBackupDir -File |
        Where-Object { $_.LastWriteTime -lt $Cutoff }
)

$DrExpired = @(
    Get-ChildItem -LiteralPath $DrBackupDir -File |
        Where-Object { $_.LastWriteTime -lt $Cutoff }
)

"local_expired=$($LocalExpired.Count)"
"dr_expired=$($DrExpired.Count)"
```

Expected result:

```text
local_expired=0
dr_expired=0
```

## Copy verification

After creating the current backup artifact:

```powershell
$NewestLocal = Get-ChildItem -LiteralPath $LocalBackupDir -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $NewestLocal) {
    throw "No local backup artifact found"
}

$Target = Join-Path $DrBackupDir $NewestLocal.Name
Copy-Item -LiteralPath $NewestLocal.FullName -Destination $Target -Force

$Copied = Get-Item -LiteralPath $Target
if ($Copied.Length -ne $NewestLocal.Length) {
    throw "DR copy size mismatch"
}

"backup=$($NewestLocal.FullName)"
"dr_copy=$($Copied.FullName)"
"bytes=$($Copied.Length)"
```

A cryptographic checksum may be added to the local procedure if required; file size equality is the minimum smoke check and is not a substitute for periodic restore testing.

## Access and encryption evidence

For privacy closeout record:
- actual local backup path;
- actual DR drive letter/path;
- encryption method/status of the removable drive;
- confirmation that only ИП Шатров has access;
- confirmation that the drive is disconnected between cycles;
- one successful 30-day rotation result;
- one successful copy verification result;
- date of the most recent restore-readiness test.

Do not record customer names, phones, e-mails or order contents in the evidence.

## Acceptance evidence

DRF-2963 is PASS only when all are true:

- local backup exists and is produced by the existing 1C procedure;
- local backup retention is verified at 30 calendar days;
- separate encrypted removable DR media is in use;
- DR copy retention is also 30 calendar days;
- owner-only access is confirmed;
- the removable drive is physically disconnected between cycles;
- no cloud/mail/messenger backup path is active;
- a restore-readiness check has been performed and documented.

If the owner explicitly chooses not to implement separate media, record that as an accepted single-device continuity risk; privacy retention may be compliant, but DR resilience remains intentionally reduced.
