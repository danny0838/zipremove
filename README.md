This package extends `zipfile` with `remove`-related functionalities.

## API

* `ZipFile.remove(zinfo_or_arcname)`

   Removes a member from the archive.  *zinfo_or_arcname* may be the full path
   of the member or a `ZipInfo` instance.

   If multiple members share the same full path, only one is removed when
   a path is provided.

   This does not physically remove the local file entry from the archive;
   the ZIP file size remains unchanged. Call `ZipFile.repack` afterwards
   to reclaim space.

   The archive must be opened with mode ``'w'``, ``'x'`` or ``'a'``.

   Returns the removed `ZipInfo` instance.

   Calling `remove` on a closed ZipFile will raise a `ValueError`.

* `ZipFile.repack(removed=None, *, strict_descriptor=False[, chunk_size])`

   Rewrites the archive to remove stale local file entries, shrinking the ZIP
   file size.

   If *removed* is provided, it must be a sequence of `ZipInfo` objects
   representing removed entries; only their corresponding local file entries
   will be removed.

   If *removed* is not provided, local file entries no longer referenced in the
   central directory will be removed.  The algorithm assumes that local file
   entries are stored consecutively:

   1. Data before the first referenced entry is removed only when it appears to
      be a sequence of consecutive entries with no extra following bytes; extra
      preceeding bytes are preserved.
   2. Data between referenced entries is removed only when it appears to
      be a sequence of consecutive entries with no extra preceding bytes; extra
      following bytes are preserved.

   ``strict_descriptor=True`` can be provided to skip the slower scan for an
   unsigned data descriptor (deprecated in the latest ZIP specification and is
   only used by legacy tools) when checking for bytes resembling a valid local
   file entry.  This improves performance, but may cause some stale local file
   entries to be preserved, as any entry using an unsigned descriptor cannot
   be detected.

   *chunk_size* may be specified to control the buffer size when moving
   entry data (default is 1 MiB).

   The archive must be opened with mode ``'a'``.

   Calling `repack` on a closed ZipFile will raise a `ValueError`.

* `ZipFile.copy(zinfo_or_arcname, new_arcname[, chunk_size])`

   Copies a member *zinfo_or_arcname* to *new_arcname* in the archive.
   *zinfo_or_arcname* may be the full path of the member or a `ZipInfo`
   instance.

   *chunk_size* may be specified to control the buffer size when copying
   entry data (default is 1 MiB).

   The archive must be opened with mode ``'w'``, ``'x'`` or ``'a'``, and the
   underlying stream must be seekable.

   Returns the original version of the copied `ZipInfo` instance.

   Calling `copy` on a closed ZipFile will raise a `ValueError`.


## Examples

### Remove files and reclaim space

```python
import os
import zipremove as zipfile

with zipfile.ZipFile('archive.zip', 'w') as zh:
    zh.writestr('file1', 'content1')
    zh.writestr('file2', 'content2')
    zh.writestr('file3', 'content3')
    zh.writestr('file4', 'content4')

print(os.path.getsize('archive.zip'))  # 398

with zipfile.ZipFile('archive.zip', 'a') as zh:
    zh.remove('file1')
    zh.remove('file2')
    zh.remove('file3')
    zh.repack()

print(os.path.getsize('archive.zip'))  # 116
```

### Remove files under a directory and reclaim space

```python
import os
import zipremove as zipfile

with zipfile.ZipFile('archive.zip', 'w') as zh:
    zh.writestr('file0', 'content0')
    zh.writestr('folder/file1', 'content1')
    zh.writestr('folder/file2', 'content2')
    zh.writestr('folder/file3', 'content3')

print(os.path.getsize('archive.zip'))  # 440

with zipfile.ZipFile('archive.zip', 'a') as zh:
    zinfos = [zh.remove(n) for n in zh.namelist() if n.startswith('folder/')]
    zh.repack(zinfos)

print(os.path.getsize('archive.zip'))  # 116
```

### Rename files under a directory and reclaim space

```python
import os
import zipremove as zipfile

with zipfile.ZipFile('archive.zip', 'w') as zh:
    zh.writestr('file0', 'content0')
    zh.writestr('folder1/file1', 'content1')
    zh.writestr('folder1/file2', 'content2')
    zh.writestr('folder1/file3', 'content3')

print(os.path.getsize('archive.zip'))  # 446

with zipfile.ZipFile('archive.zip', 'a') as zh:
    for n in zh.namelist():
        if n.startswith('folder1/'):
            n2 = 'folder2/' + n[len('folder1/'):]
            zh.copy(n, n2)
            zh.remove(n)
    zh.repack()

print(os.path.getsize('archive.zip'))  # 446
```
