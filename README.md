![PyPI version](https://img.shields.io/pypi/v/zipremove.svg)
![Python Versions](https://img.shields.io/pypi/pyversions/zipremove)
![Status](https://img.shields.io/pypi/status/zipremove)
![License](https://img.shields.io/github/license/danny0838/zipremove)
[![Downloads](https://static.pepy.tech/personalized-badge/zipremove?period=month&left_text=Downloads)](https://pepy.tech/project/zipremove)
[![Pull request](https://img.shields.io/github/pulls/detail/state/python/cpython/134627)](https://github.com/python/cpython/pull/134627)

This package extends `zipfile` with `remove`-related functionalities.

## API

* `ZipFile.remove(zinfo_or_arcname)`

   Removes a member from the archive.  *zinfo_or_arcname* may be the full path
   of the member or a `ZipInfo` instance.

   If multiple members share the same full path, only one is removed when
   a path is provided.

   This does not physically remove the local file entry from the archive.
   Call `ZipFile.repack` afterwards to reclaim space.

   The archive must be opened with mode ``'w'``, ``'x'`` or ``'a'``.

   Returns the removed `ZipInfo` instance.

   Calling `remove` on a closed ZipFile will raise a `ValueError`.

* `ZipFile.repack(removed=None, *, strict_descriptor=False[, chunk_size])`

   Rewrites the archive to remove stale local file entries, shrinking its file
   size.

   If *removed* is provided, it must be a sequence of `ZipInfo` objects
   representing removed entries; only their corresponding local file entries
   will be removed.

   If *removed* is not provided, the archive is scanned to identify and remove
   local file entries that are no longer referenced in the central directory.
   The algorithm assumes that local file entries (and the central directory,
   which is mostly treated as the "last entry") are stored consecutively:

   1. Data before the first referenced entry is removed only when it appears to
      be a sequence of consecutive entries with no extra following bytes; extra
      preceding bytes are preserved.
   2. Data between referenced entries is removed only when it appears to
      be a sequence of consecutive entries with no extra preceding bytes; extra
      following bytes are preserved.
   3. Entries must not overlap. If any entry's data overlaps with another, a
      `BadZipFile` error is raised and no changes are made.

   When scanning, setting `strict_descriptor=True` disables detection of any
   entry using an unsigned data descriptor (deprecated in the ZIP specification
   since version 6.3.0, released on 2006-09-29, and used only by some legacy
   tools). This improves performance, but may cause some stale entries to be
   preserved.

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

### Remove entries and reclaim space

Call `repack` after `remove`s to reclaim the space of the removed entries:

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

print(os.path.getsize('archive.zip'))  # 116 (would be 245 without `repack`)
```

Alternatively, pass the ZipInfo objects of the removed entries, for better
performance and error-proofing:

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
    zinfos = []
    zinfos.append(zh.remove('file1'))
    zinfos.append(zh.remove('file2'))
    zinfos.append(zh.remove('file3'))
    zh.repack(zinfos)

print(os.path.getsize('archive.zip'))  # 116 (would be 245 without `repack`)
```

### Move entries under a folder and reclaim space

Moving entries in a ZIP file must be done as a combination of `copy`, `remove`,
and optionally `repack`, because every local file entry contains the filename
and requires rewriting.

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

print(os.path.getsize('archive.zip'))  # 446 (would be 599 without `repack`)
```

Similarly, pass the ZipInfo objects of the copied/removed entries for better
performance and error-proofing:

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
    zinfos = []
    for n in zh.namelist():
        if n.startswith('folder1/'):
            n2 = 'folder2/' + n[len('folder1/'):]
            zinfos.append(zh.remove(zh.copy(n, n2)))
    zh.repack(zinfos)

print(os.path.getsize('archive.zip'))  # 446 (would be 599 without `repack`)
```
