![PyPI version](https://img.shields.io/pypi/v/zipremove.svg)
![Python Versions](https://img.shields.io/pypi/pyversions/zipremove)
![Status](https://img.shields.io/pypi/status/zipremove)
![License](https://img.shields.io/github/license/danny0838/zipremove)
[![Downloads](https://static.pepy.tech/personalized-badge/zipremove?period=month&left_text=Downloads)](https://pepy.tech/project/zipremove)
[![Pull request](https://img.shields.io/github/pulls/detail/state/python/cpython/134627)](https://github.com/python/cpython/pull/134627)

This package extends `zipfile.ZipFile` with remove-related capabilities.

## API

* `ZipFile.remove(zinfo_or_arcname)`

   Removes a member entry from the archive's central directory.
   *zinfo_or_arcname* may be the full path of the member or a `ZipInfo`
   instance.  If multiple members share the same path and a string is
   provided, only one unspecified entry is removed; pass a specific
   `ZipInfo` instance to guarantee which member is removed.

   The archive must be opened with mode ``'w'``, ``'x'`` or ``'a'``.

   Returns the removed `ZipInfo` instance.

   Calling `remove` on a closed ZipFile will raise a `ValueError`.

   > **Note:** 
   > This method only removes the member's entry from the central directory,
   > making it inaccessible to most tools.  The member's local file entry,
   > including content and metadata, remains in the archive and is still
   > forensically recoverable.  To completely delete the data and reclaim
   > space, call `repack` afterwards (preferably passing the returned `ZipInfo`
   > instance).

* `ZipFile.repack(removed=None, *, strict_descriptor=True[, chunk_size])`

   Rewrites the archive to remove unreferenced local file entries, shrinking
   its file size.  The archive must be opened with mode ``'a'``.

   If *removed* is provided, it must be a sequence of `ZipInfo` objects
   representing the recently removed members, and only their corresponding
   local file entries will be removed.  This is the most efficient and reliable
   way to reclaim space.  A brief example looks like:

   ```python
   with ZipFile('spam.zip', 'a') as myzip:
       removed = [myzip.remove(name) for name in ('ham.txt', 'eggs.txt')]
       myzip.repack(removed)
   ```

   If *removed* is omitted, the archive is scanned to locate and remove local
   file entries that are no longer referenced in the central directory.

   When scanning, *strict_descriptor* controls how entries with an unsigned
   data descriptor are handled.  A data descriptor is an optional record
   (mostly used for non-seekable streaming) stored after an entry's data, and
   can be either signed (beginning with a magic signature) or unsigned.
   Unsigned descriptors have been deprecated by the [PKZIP Application Note]
   since version 6.3.0 (released in 2006) and are rarely produced by modern
   tools.

   When *strict_descriptor* is true (the default), unsigned descriptors are
   not detectable, and unreferenced entries using them are not recognized and
   their space is not reclaimed.  Setting `strict_descriptor=False` allows
   such entries to be properly handled, at the cost of a significantly slower
   scan—around 100 to 1000 times in the worst case—which may be exploitable
   as a denial-of-service vector on untrusted input.  Entries without a
   descriptor or with a signed descriptor are unaffected.

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

   > **Note:** 
   > Renaming a member in a ZIP file requires rewriting its data, as the
   > filename is stored within its local file entry.
   >
   > To rename a member and reclaim the space occupied by the old entry,
   > combine `copy`, `remove`, and `repack` like:
   >
   > ```python
   > with ZipFile('spam.zip', 'a') as myzip:
   >     myzip.repack([myzip.remove(myzip.copy('old.txt', 'new.txt'))])
   > ```

## Examples

### Remove entries and reclaim space

Call `repack` after `remove`s to reclaim the space of the removed entries:

```python
import os
from zipremove import ZipFile

with ZipFile('archive.zip', 'w') as zh:
    zh.writestr('file1', 'content1')
    zh.writestr('file2', 'content2')
    zh.writestr('file3', 'content3')
    zh.writestr('file4', 'content4')

print(os.path.getsize('archive.zip'))  # 398

with ZipFile('archive.zip', 'a') as zh:
    zh.remove('file1')
    zh.remove('file2')
    zh.remove('file3')
    zh.repack()

print(os.path.getsize('archive.zip'))  # 116 (would be 245 without `repack`)
```

Alternatively, pass the ZipInfo objects of the removed entries, which is
*highly recommended* due to better performance and error-proofing:

```python
import os
from zipremove import ZipFile

with ZipFile('archive.zip', 'w') as zh:
    zh.writestr('file1', 'content1')
    zh.writestr('file2', 'content2')
    zh.writestr('file3', 'content3')
    zh.writestr('file4', 'content4')

print(os.path.getsize('archive.zip'))  # 398

with ZipFile('archive.zip', 'a') as zh:
    # A generator expression doesn't work here since a `remove` cannot run
    # during a `repack` due to writing protection and thread lock.
    zh.repack([zh.remove(fn) for fn in (
        'file1',
        'file2',
        'file3',
    )])

print(os.path.getsize('archive.zip'))  # 116 (would be 245 without `repack`)
```

### Move entries under a folder and reclaim space

Moving an entry can be done as a combination of `copy`, `remove`, and
`repack`:

```python
import os
from zipremove import ZipFile

with ZipFile('archive.zip', 'w') as zh:
    zh.writestr('file0', 'content0')
    zh.writestr('folder1/file1', 'content1')
    zh.writestr('folder1/file2', 'content2')
    zh.writestr('folder1/file3', 'content3')

print(os.path.getsize('archive.zip'))  # 446

with ZipFile('archive.zip', 'a') as zh:
    fsrc, fdst = 'folder1/', 'folder2/'
    for fn in zh.namelist():
        if fn.startswith(fsrc):
            zh.remove(zh.copy(fn, fdst + fn[len(fsrc):]))
    zh.repack()

print(os.path.getsize('archive.zip'))  # 446 (would be 599 without `repack`)
```

Similarly, pass the ZipInfo objects of the removed entries for better
performance and error-proofing:

```python
import os
from zipremove import ZipFile

with ZipFile('archive.zip', 'w') as zh:
    zh.writestr('file0', 'content0')
    zh.writestr('folder1/file1', 'content1')
    zh.writestr('folder1/file2', 'content2')
    zh.writestr('folder1/file3', 'content3')

print(os.path.getsize('archive.zip'))  # 446

with ZipFile('archive.zip', 'a') as zh:
    fsrc, fdst = 'folder1/', 'folder2/'
    # A generator expression doesn't work here since a `remove` cannot run
    # during a `repack` due to writing protection and thread lock.
    zh.repack([
        zh.remove(zh.copy(fn, fdst + fn[len(fsrc):]))
        for fn in zh.namelist()
        if fn.startswith(fsrc)
    ])

print(os.path.getsize('archive.zip'))  # 446 (would be 599 without `repack`)
```

[PKZIP Application Note]: https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
