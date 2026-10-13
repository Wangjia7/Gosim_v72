# Agent observer starter kit — Documents backup

The 6 related folders and 2 standalone ZIP files are backed up in [this repository release](https://github.com/Wangjia7/Gosim_v72/releases/tag/starter-documents-backup-2026-10-13). Original paths relative to Documents are preserved.

Download all `starter-documents.tar.gz.partNNN` files and `MANIFEST.json` from the release. On macOS/Linux, reconstruct and extract with:

```sh
cat starter-documents.tar.gz.part* > starter-documents.tar.gz
tar -xzf starter-documents.tar.gz
```

`MANIFEST.json` lists every source file, original SHA-256, uploaded SHA-256, and the checksum of each part. API secrets have been replaced with `REDACTED_API_SECRET`, including copies inside ZIP files. Original sensitive configurations and Git metadata are preserved separately on the owner's local computer, and are excluded from the public backup.
