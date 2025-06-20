# Changelog

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
