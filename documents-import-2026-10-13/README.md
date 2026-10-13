# Documents Gosim migration — 2026-10-13

These 14 folders retain their paths relative to the original Documents folder.
All files, including hidden files and generated results, are included.
Nested `.git` directories are saved as `.git-backup.tar.gz` beside their original location; extract the archive to restore them.
`MANIFEST.json` records every original file's SHA-256, size, permissions, timestamps, and directories (including empty directories).
Git does not preserve empty directories or original timestamps; use the manifest to restore these if needed.
