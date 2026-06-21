![PyPI version](https://img.shields.io/pypi/v/zipremove.svg)
![Python Versions](https://img.shields.io/pypi/pyversions/zipremove)
![Status](https://img.shields.io/pypi/status/zipremove)
![License](https://img.shields.io/github/license/danny0838/zipremove)
[![Downloads](https://static.pepy.tech/personalized-badge/zipremove?period=month&left_text=Downloads)](https://pepy.tech/project/zipremove)
[![Pull request](https://img.shields.io/github/pulls/detail/state/python/cpython/134627)](https://github.com/python/cpython/pull/134627)

This package extends `zipfile` with `remove`-related functionalities.

## API

* `ZipFile.remove(zinfo_or_arcname)`

   Removes a member entry from the archive's central directory.
   *zinfo_or_arcname* may be the full path of the member or a `ZipInfo`
   instance.  If multiple members share the same full path and the path is
   given as a string, only one of them is removed and which one is
   unspecified; it should not be relied upon.  Pass the specific
   `ZipInfo` instance to remove a particular member.

   The archive must be opened with mode ``'w'``, ``'x'`` or ``'a'``.

   Returns the removed `ZipInfo` instance.

   Calling `remove` on a closed ZipFile will raise a `ValueError`.

   > **Note:** 
   > This method only removes the member's entry from the central directory,
   > making it inaccessible to most tools.  The member's local file entry,
   > including content and metadata, remains in the archive and is still
   > recoverable using forensic tools.  Call `repack` afterwards to remove the
   > local file entry and reclaim space; pass the returned `ZipInfo` to
   > `repack` to ensure the data is removed regardless of how the entry was
   > written.

* `ZipFile.repack(removed=None, *, strict_descriptor=True[, chunk_size])`

   Rewrites the archive to remove unreferenced local file entries, shrinking
   its file size.  The archive must be opened with mode ``'a'``.

   If *removed* is provided, it must be a sequence of `ZipInfo` objects
   representing the recently removed members, and only their corresponding
   local file entries will be removed.  Otherwise, the archive is scanned to
   locate and remove local file entries that are no longer referenced in the
   central directory.

   Passing *removed* is the most reliable way to reclaim space: the
   corresponding local file entries are located directly from the central
   directory and removed regardless of how they were written, whereas the scan
   used when *removed* is omitted may leave some entries in place (see
   *strict_descriptor* below).  To remove members and reclaim their space in a
   single step:

   ```python
    with ZipFile('spam.zip', 'a') as myzip:
        removed = [myzip.remove(name) for name in ('ham.txt', 'eggs.txt')]
        myzip.repack(removed)
   ```

   When scanning, *strict_descriptor* controls how entries written with an
   unsigned *data descriptor* are handled.  A data descriptor is an optional
   record holding an entry's CRC and sizes, stored just after the entry's data;
   it is used when the archive is written to a non-seekable stream, and is
   *signed* when it begins with a marker signature or *unsigned* otherwise.
   Unsigned descriptors have been deprecated by the [PKZIP Application Note]
   since version 6.3.0 (released in 2006) and are written only by some legacy
   tools; signed descriptors—written by Python and other modern tools—are always
   detected.  When *strict_descriptor* is true (the default), only signed data
   descriptors are detected, so an unreferenced entry written with an unsigned
   descriptor is not located and its space is not reclaimed by the scan.
   Setting ``strict_descriptor=False`` additionally detects unsigned
   descriptors, at the cost of a significantly slower scan—around 100 to 1000
   times in the worst case—which may be exploitable as a denial-of-service
   vector on untrusted input.  This does not affect entries without a data
   descriptor, and is not needed when *removed* is provided.

   *chunk_size* may be specified to control the buffer size when moving
   entry data (default is 1 MiB).

   Calling `repack` on a closed ZipFile will raise a `ValueError`.

   > **Note:** 
   > The scanning algorithm is heuristic-based and assumes that the ZIP file
   > is normally structured—for example, with local file entries stored
   > consecutively, without overlap or interleaved binary data.  Prepended
   > binary data, such as a self-extractor stub, is recognized and preserved
   > unless it happens to contain bytes that coincidentally resemble a valid
   > local file entry in multiple respects—an extremely rare case. Embedded
   > ZIP payloads are also handled correctly, as long as they follow normal
   > structure.  However, the algorithm does not guarantee correctness or
   > safety on untrusted or intentionally crafted input.  It is generally
   > recommended to provide the *removed* argument for better reliability and
   > performance.

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

[PKZIP Application Note]: https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
