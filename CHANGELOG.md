# Changelog

## [0.7.0] - 2025-08-31
* Fixed a compatibility issue for older `tox`.
* Dev dependencies are now handled with `requirements-*.txt` files rather than `extras_require`.
* Miscellaneous improvements to the dev tools.

## [0.6.1] - 2025-07-22
* Removed `zipfile.data_offset` updating since it has been removed.

## [0.6.0] - 2025-07-03
* `repack` now updates `data_offset` for `ZipFile`.
* Adjusted the default buffer size for several intetnal methods used by `repack`.

## [0.5.0] - 2025-06-21
* `repack` now clears `_end_offset` for all referenced `ZipInfo` objects.
* Optimized `copy` by using shallow copy instead.

## [0.4.1] - 2025-06-20
* Internal code optimization.

## [0.4.0] - 2025-06-18
* Fixed an issue where an encrypted and compressed local file entry with an unsigned data descriptor cannot be detected.
* Improved polyfill for `LZMADecompressor`.

## [0.3.0] - 2025-06-17
* `import *` now imports the same identifiers as the standard `zipfile` module.
* Enhanced scanning of unsigned data descriptors for LZMA-compressed entries.

## [0.2.0] - 2025-06-16
* `strict_descriptor=True` now strictly prevents any scanning of unsigned data descriptors.
