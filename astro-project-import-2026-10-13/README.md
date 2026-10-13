# Astronomy agent project — observer/Gosim backup

The observer/Gosim project folders and their supporting files are backed up in [this repository release](https://github.com/Wangjia7/Gosim_v72/releases/tag/astro-project-backup-2026-10-13). Original paths relative to Documents are preserved.

Download all `astro-project.tar.gz.partNNN` files and `MANIFEST.json` from the release. On macOS/Linux, reconstruct and extract with:

```sh
cat astro-project.tar.gz.part* > astro-project.tar.gz
tar -xzf astro-project.tar.gz
```

`MANIFEST.json` lists every source file, original SHA-256, uploaded SHA-256, and the checksum of each part. API secrets have been replaced with `REDACTED_API_SECRET`, including copies inside ZIP files. Sensitive configurations are preserved locally. Only original files of at least 10 MiB are removed after backup verification; smaller source files and project directories remain.
