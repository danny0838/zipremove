import copy
import io
import os
import struct
from zipfile import *
from zipfile import __all__  # noqa: F401
from zipfile import _get_compressor  # noqa: F401
from zipfile import (
    _DD_SIGNATURE,
    _FH_COMPRESSED_SIZE,
    _FH_COMPRESSION_METHOD,
    _FH_CRC,
    _FH_EXTRA_FIELD_LENGTH,
    _FH_FILENAME_LENGTH,
    _FH_GENERAL_PURPOSE_FLAG_BITS,
    _FH_SIGNATURE,
    _FH_UNCOMPRESSED_SIZE,
    LZMADecompressor,
    _get_decompressor,
    crc32,
    sizeFileHeader,
    stringFileHeader,
    structFileHeader,
)

# polyfills
try:
    ZIP_ZSTANDARD
except NameError:
    # polyfill for Python < 3.14
    ZIP_ZSTANDARD = 93

try:
    from zipfile import _MASK_ENCRYPTED
except ImportError:
    # polyfill for Python < 3.11
    _MASK_ENCRYPTED = 1 << 0

try:
    from zipfile import _MASK_USE_DATA_DESCRIPTOR
except ImportError:
    # polyfill for Python < 3.11
    _MASK_USE_DATA_DESCRIPTOR = 1 << 3

try:
    from zipfile import _sanitize_filename
except ImportError:
    # polyfill for Python < 3.11
    def _sanitize_filename(filename):
        null_byte = filename.find(chr(0))
        if null_byte >= 0:
            filename = filename[0:null_byte]
        if os.sep != "/" and os.sep in filename:
            filename = filename.replace(os.sep, "/")
        if os.altsep and os.altsep != "/" and os.altsep in filename:
            filename = filename.replace(os.altsep, "/")
        return filename

try:
    LZMADecompressor().unused_data
except AttributeError:
    # polyfill to support LZMADecompressor().unused_data
    @property
    def unused_data(self):
        try:
            return self._decomp.unused_data
        except AttributeError:
            return b''
    LZMADecompressor.unused_data = unused_data


class _ZipRepacker:
    """Class for ZipFile repacking."""
    def __init__(self, *, strict_descriptor=False, chunk_size=2**20, debug=0):
        self.debug = debug  # Level of printing: 0 through 3
        self.chunk_size = chunk_size
        self.strict_descriptor = strict_descriptor

    def _debug(self, level, *msg):
        if self.debug >= level:
            print(*msg)

    def copy(self, zfile, zinfo, filename):
        # make a copy of zinfo
        zinfo2 = copy.copy(zinfo)

        # apply sanitized new filename as in `ZipInfo.__init__`
        zinfo2.orig_filename = filename
        zinfo2.filename = _sanitize_filename(filename)

        zinfo2.header_offset = zfile.start_dir

        # polyfill: clear zinfo2._end_offset if exists
        # (Python >= 3.8 with fix #109858)
        if hasattr(zinfo2, '_end_offset'):
            zinfo2._end_offset = None

        # write to a new local file header
        fp = zfile.fp
        sizes = self._calc_local_file_entry_size(fp, zinfo)
        fp.seek(zinfo2.header_offset)
        fp.write(zinfo2.FileHeader())
        self._copy_bytes(fp, zinfo.header_offset + sum(sizes[:3]), fp.tell(), sum(sizes[3:]))
        zfile.start_dir = fp.tell()

        # add to filelist
        zfile.filelist.append(zinfo2)
        zfile.NameToInfo[zinfo2.filename] = zinfo2

        zfile._didModify = True

    def repack(self, zfile, removed=None):
        """
        Repack the ZIP file, stripping unreferenced local file entries.

        Assumes that local file entries (and the central directory, which is
        mostly treated as the "last entry") are stored consecutively, with no
        gaps or overlaps:

        1. If any referenced entry overlaps with another, a `BadZipFile` error
           is raised since safe repacking cannot be guaranteed.

        2. Data before the first referenced entry is stripped only when it
           appears to be a sequence of consecutive entries with no extra
           following bytes; extra preceeding bytes are preserved.

        3. Data between referenced entries is stripped only when it appears to
           be a sequence of consecutive entries with no extra preceding bytes;
           extra following bytes are preserved.

        This is to prevent an unexpected data removal (false positive), though
        a false negative may happen in certain rare cases.

        Examples:

        Stripping before the first referenced entry:

            [random bytes]
            [unreferenced local file entry]
            [random bytes]
            <-- stripping start
            [unreferenced local file entry]
            [unreferenced local file entry]
            <-- stripping end
            [local file entry 1] (or central directory)
            ...

        Stripping between referenced entries:

            ...
            [local file entry]
            <-- stripping start
            [unreferenced local file entry]
            [unreferenced local file entry]
            <-- stripping end
            [random bytes]
            [unreferenced local file entry]
            [random bytes]
            [local file entry] (or central directory)
            ...

        No stripping:

            [unreferenced local file entry]
            [random bytes]
            [local file entry 1] (or central directory)
            ...

        No stripping:

            ...
            [local file entry]
            [random bytes]
            [unreferenced local file entry]
            [local file entry] (or central directory)
            ...

        Side effects:
            - Modifies the ZIP file in place.
            - Updates zfile.start_dir and zfile.data_offset to account for
              removed data.
            - Sets zfile._didModify to True.
            - Updates header_offset and clears _end_offset of referenced
              ZipInfo instances.

        Parameters:
            zfile: A ZipFile object representing the archive to repack.
            removed: Optional. A sequence of ZipInfo instances representing
                the previously removed entries. When provided, only their
                corresponding local file entries are stripped.
        """
        removed_zinfos = set(removed or ())

        fp = zfile.fp

        # get a sorted filelist by header offset, in case the dir order
        # doesn't match the actual entry order
        filelist = (*zfile.filelist, *removed_zinfos)
        filelist = sorted(filelist, key=lambda x: x.header_offset)

        # calculate each entry size and validate
        entry_size_list = []
        used_entry_size_list = []
        for i, zinfo in enumerate(filelist):
            try:
                offset = filelist[i + 1].header_offset
            except IndexError:
                offset = zfile.start_dir
            entry_size = offset - zinfo.header_offset

            # may raise on an invalid local file header
            used_entry_size = sum(self._calc_local_file_entry_size(fp, zinfo))

            self._debug(3, 'entry:', i, zinfo.orig_filename,
                        zinfo.header_offset, entry_size, used_entry_size)
            if used_entry_size > entry_size:
                raise BadZipFile(
                    f"Overlapped entries: {zinfo.orig_filename!r} ")

            if removed is not None and zinfo not in removed_zinfos:
                used_entry_size = entry_size

            entry_size_list.append(entry_size)
            used_entry_size_list.append(used_entry_size)

        # calculate the starting entry offset (bytes to skip)
        if removed is None:
            try:
                offset = filelist[0].header_offset
            except IndexError:
                offset = zfile.start_dir
            entry_offset = self._calc_initial_entry_offset(fp, offset)
        else:
            entry_offset = 0

        # move file entries
        for i, zinfo in enumerate(filelist):
            entry_size = entry_size_list[i]
            used_entry_size = used_entry_size_list[i]

            # update the header and move entry data to the new position
            old_header_offset = zinfo.header_offset
            zinfo.header_offset -= entry_offset

            if zinfo in removed_zinfos:
                self._copy_bytes(
                    fp,
                    old_header_offset + used_entry_size,
                    zinfo.header_offset,
                    entry_size - used_entry_size,
                )

                # update entry_offset for subsequent files to follow
                entry_offset += used_entry_size

            else:
                if entry_offset > 0:
                    self._copy_bytes(
                        fp,
                        old_header_offset,
                        zinfo.header_offset,
                        used_entry_size,
                    )

                stale_entry_size = self._validate_local_file_entry_sequence(
                    fp,
                    old_header_offset + used_entry_size,
                    old_header_offset + entry_size,
                )

                if stale_entry_size > 0:
                    self._copy_bytes(
                        fp,
                        old_header_offset + used_entry_size + stale_entry_size,
                        zinfo.header_offset + used_entry_size,
                        entry_size - used_entry_size - stale_entry_size,
                    )

                    # update entry_offset for subsequent files to follow
                    entry_offset += stale_entry_size

        # update state
        zfile.start_dir -= entry_offset
        zfile._didModify = True

        # polyfill: update _data_offset if exists
        if getattr(zfile, '_data_offset', None):
            try:
                offset = filelist[0].header_offset
            except IndexError:
                offset = zfile.start_dir
            if offset < zfile._data_offset:
                zfile._data_offset = offset

        # polyfill: clear ZipInfo._end_offset if exists
        # (Python >= 3.8 with fix #109858)
        if hasattr(ZipInfo, '_end_offset'):
            for zinfo in filelist:
                zinfo._end_offset = None

    def _calc_initial_entry_offset(self, fp, data_offset):
        checked_offsets = {}
        if data_offset > 0:
            self._debug(3, 'scanning file signatures before:', data_offset)
            for pos in self._iter_scan_signature(fp, stringFileHeader, 0, data_offset):
                self._debug(3, 'checking file signature at:', pos)
                entry_size = self._validate_local_file_entry_sequence(
                    fp, pos, data_offset, checked_offsets)
                if entry_size == data_offset - pos:
                    return entry_size
        return 0

    def _iter_scan_signature(self, fp, signature, start_offset, end_offset,
                             chunk_size=io.DEFAULT_BUFFER_SIZE):
        sig_len = len(signature)
        remainder = b''
        pos = start_offset

        while pos < end_offset:
            # required for each loop since fp may be changed during each yield
            fp.seek(pos)

            chunk = remainder + fp.read(min(chunk_size, end_offset - pos))

            delta = pos - len(remainder)
            idx = 0
            while True:
                idx = chunk.find(signature, idx)
                if idx == -1:
                    break

                yield delta + idx
                idx += 1

            remainder = chunk[-(sig_len - 1):]
            pos += chunk_size

    def _validate_local_file_entry_sequence(self, fp, start_offset, end_offset, checked_offsets=None):
        offset = start_offset

        while offset < end_offset:
            self._debug(3, 'checking local file entry at:', offset)

            # Cache checked offsets to improve performance.
            try:
                entry_size = checked_offsets[offset]
            except (KeyError, TypeError):
                entry_size = self._validate_local_file_entry(fp, offset, end_offset)
                if checked_offsets is not None:
                    checked_offsets[offset] = entry_size
            else:
                self._debug(3, 'read from checked cache:', offset)

            if entry_size is None:
                break

            offset += entry_size

        return offset - start_offset

    def _validate_local_file_entry(self, fp, offset, end_offset):
        fp.seek(offset)
        try:
            fheader = self._read_local_file_header(fp)
        except BadZipFile:
            return None

        # Create a dummy ZipInfo to utilize parsing.
        # Flush only the required information.
        zinfo = ZipInfo()
        zinfo.header_offset = offset
        zinfo.flag_bits = fheader[_FH_GENERAL_PURPOSE_FLAG_BITS]
        zinfo.compress_size = fheader[_FH_COMPRESSED_SIZE]
        zinfo.file_size = fheader[_FH_UNCOMPRESSED_SIZE]
        zinfo.CRC = fheader[_FH_CRC]

        filename = fp.read(fheader[_FH_FILENAME_LENGTH])
        zinfo.extra = fp.read(fheader[_FH_EXTRA_FIELD_LENGTH])
        pos = fp.tell()

        if pos > end_offset:
            return None

        # parse zip64
        try:
            try:
                zinfo._decodeExtra(crc32(filename))
            except TypeError:
                # polyfill for Python < 3.12
                zinfo._decodeExtra()
        except BadZipFile:
            return None

        dd_size = 0

        if zinfo.flag_bits & _MASK_USE_DATA_DESCRIPTOR:
            # According to the spec, these fields should be zero when data
            # descriptor is used. Otherwise treat as a false positive on
            # random bytes to return early, as scanning for data descriptor
            # is rather expensive.
            if not (zinfo.CRC == zinfo.compress_size == zinfo.file_size == 0):
                return None

            zip64 = fheader[_FH_UNCOMPRESSED_SIZE] == 0xffffffff

            dd = self._scan_data_descriptor(fp, pos, end_offset, zip64)
            if dd is None and not self.strict_descriptor:
                if zinfo.flag_bits & _MASK_ENCRYPTED:
                    dd = False
                else:
                    dd = self._scan_data_descriptor_no_sig_by_decompression(
                        fp, pos, end_offset, zip64, fheader[_FH_COMPRESSION_METHOD])
                if dd is False:
                    dd = self._scan_data_descriptor_no_sig(fp, pos, end_offset, zip64)
            if dd is None:
                return None

            zinfo.CRC, zinfo.compress_size, zinfo.file_size, dd_size = dd

        return (
            sizeFileHeader +
            fheader[_FH_FILENAME_LENGTH] + fheader[_FH_EXTRA_FIELD_LENGTH] +
            zinfo.compress_size +
            dd_size
        )

    def _read_local_file_header(self, fp):
        fheader = fp.read(sizeFileHeader)
        if len(fheader) != sizeFileHeader:
            raise BadZipFile("Truncated file header")
        fheader = struct.unpack(structFileHeader, fheader)
        if fheader[_FH_SIGNATURE] != stringFileHeader:
            raise BadZipFile("Bad magic number for file header")
        return fheader

    def _scan_data_descriptor(self, fp, offset, end_offset, zip64):
        dd_fmt = '<LLQQ' if zip64 else '<LLLL'
        dd_size = struct.calcsize(dd_fmt)

        # scan for signature and take the first valid descriptor
        for pos in self._iter_scan_signature(
            fp, struct.pack('<L', _DD_SIGNATURE), offset, end_offset
        ):
            fp.seek(pos)
            dd = fp.read(min(dd_size, end_offset - pos))
            try:
                _, crc, compress_size, file_size = struct.unpack(dd_fmt, dd)
            except struct.error:
                continue

            # @TODO: also check CRC to better guard from a false positive?
            if pos - offset != compress_size:
                continue

            return crc, compress_size, file_size, dd_size

        return None

    def _scan_data_descriptor_no_sig(self, fp, offset, end_offset, zip64, chunk_size=8192):
        dd_fmt = '<LQQ' if zip64 else '<LLL'
        dd_size = struct.calcsize(dd_fmt)

        pos = offset
        remainder = b''

        fp.seek(offset)
        while pos < end_offset:
            chunk = remainder + fp.read(min(chunk_size, end_offset - pos))

            delta = pos - len(remainder) - offset
            mv = memoryview(chunk)
            for i in range(len(chunk) - dd_size + 1):
                dd = mv[i:i + dd_size]
                try:
                    crc, compress_size, file_size = struct.unpack(dd_fmt, dd)
                except struct.error:
                    continue
                if delta + i != compress_size:
                    continue

                return crc, compress_size, file_size, dd_size

            remainder = chunk[-(dd_size - 1):]
            pos += chunk_size

        return None

    def _scan_data_descriptor_no_sig_by_decompression(self, fp, offset, end_offset, zip64, method):
        try:
            decompressor = _get_decompressor(method)
        except RuntimeError:
            return False

        if decompressor is None:
            return False

        dd_fmt = '<LQQ' if zip64 else '<LLL'
        dd_size = struct.calcsize(dd_fmt)

        # early return and prevent potential `fp.read(-1)`
        if end_offset - dd_size < offset:
            return None

        try:
            pos = self._trace_compressed_block_end(fp, offset, end_offset - dd_size, decompressor)
        except Exception:
            return None

        fp.seek(pos)
        dd = fp.read(dd_size)
        try:
            crc, compress_size, file_size = struct.unpack(dd_fmt, dd)
        except struct.error:
            return None
        if pos - offset != compress_size:
            return None

        return crc, compress_size, file_size, dd_size

    def _trace_compressed_block_end(self, fp, offset, end_offset, decompressor,
                                    chunk_size=io.DEFAULT_BUFFER_SIZE):
        fp.seek(offset)
        read_size = 0
        while True:
            chunk = fp.read(min(chunk_size, end_offset - offset - read_size))
            if not chunk:
                raise EOFError('Unexpected EOF while decompressing')

            # may raise on error
            decompressor.decompress(chunk)

            read_size += len(chunk)

            if decompressor.eof:
                unused_len = len(decompressor.unused_data)
                return offset + read_size - unused_len

    def _calc_local_file_entry_size(self, fp, zinfo):
        fp.seek(zinfo.header_offset)
        fheader = self._read_local_file_header(fp)

        if zinfo.flag_bits & _MASK_USE_DATA_DESCRIPTOR:
            zip64 = fheader[_FH_UNCOMPRESSED_SIZE] == 0xffffffff
            dd_fmt = '<LLQQ' if zip64 else '<LLLL'
            fp.seek(
                fheader[_FH_FILENAME_LENGTH] + fheader[_FH_EXTRA_FIELD_LENGTH] +
                zinfo.compress_size,
                os.SEEK_CUR,
            )
            if fp.read(struct.calcsize('<L')) != struct.pack('<L', _DD_SIGNATURE):
                dd_fmt = '<LQQ' if zip64 else '<LLL'
            dd_size = struct.calcsize(dd_fmt)
        else:
            dd_size = 0

        return (
            sizeFileHeader,
            fheader[_FH_FILENAME_LENGTH],
            fheader[_FH_EXTRA_FIELD_LENGTH],
            zinfo.compress_size,
            dd_size,
        )

    def _copy_bytes(self, fp, old_offset, new_offset, size):
        read_size = 0
        while read_size < size:
            fp.seek(old_offset + read_size)
            data = fp.read(min(size - read_size, self.chunk_size))
            fp.seek(new_offset + read_size)
            fp.write(data)
            fp.flush()
            read_size += len(data)


class ZipFile(ZipFile):
    def copy(self, zinfo_or_arcname, filename, *, chunk_size=2**20):
        """Copy a member in the archive."""
        if self.mode not in ('w', 'x', 'a'):
            raise ValueError("copy() requires mode 'w', 'x', or 'a'")
        if not self.fp:
            raise ValueError(
                "Attempt to write to ZIP archive that was already closed")
        if self._writing:
            raise ValueError(
                "Can't write to ZIP archive while an open writing handle exists."
            )
        if not self._seekable:
            raise io.UnsupportedOperation("copy() requires a seekable stream.")

        with self._lock:
            # get the zinfo
            # raise KeyError if arcname does not exist
            if isinstance(zinfo_or_arcname, ZipInfo):
                zinfo = zinfo_or_arcname
                if zinfo not in self.filelist:
                    raise KeyError('There is no item %r in the archive' % zinfo)
            else:
                zinfo = self.getinfo(zinfo_or_arcname)

            self._writing = True
            try:
                _ZipRepacker(chunk_size=chunk_size).copy(self, zinfo, filename)
            finally:
                self._writing = False

        return zinfo

    def remove(self, zinfo_or_arcname):
        """Remove a member from the archive."""
        if self.mode not in ('w', 'x', 'a'):
            raise ValueError("remove() requires mode 'w', 'x', or 'a'")
        if not self.fp:
            raise ValueError(
                "Attempt to write to ZIP archive that was already closed")
        if self._writing:
            raise ValueError(
                "Can't write to ZIP archive while an open writing handle exists."
            )

        with self._lock:
            # get the zinfo
            if isinstance(zinfo_or_arcname, ZipInfo):
                zinfo = zinfo_or_arcname
            else:
                # raise KeyError if arcname does not exist
                zinfo = self.getinfo(zinfo_or_arcname)

            try:
                self.filelist.remove(zinfo)
            except ValueError:
                raise KeyError('There is no item %r in the archive' % zinfo) from None

            try:
                del self.NameToInfo[zinfo.filename]
            except KeyError:
                pass

            # Avoid missing entry if there is another entry having the same name,
            # to prevent an error on `testzip()`.
            # Reverse the order as NameToInfo normally stores the last added one.
            for zi in reversed(self.filelist):
                if zi.filename == zinfo.filename:
                    self.NameToInfo.setdefault(zi.filename, zi)
                    break

            self._didModify = True

        return zinfo

    def repack(self, removed=None, **opts):
        """Repack a zip file, removing non-referenced file entries.

        The archive must be opened with mode 'a', as mode 'w'/'x' do not
        truncate the file when closed. This cannot be simplely changed as
        they may be used on an unseekable file buffer, which disallows
        truncation."""
        if self.mode != 'a':
            raise ValueError("repack() requires mode 'a'")
        if not self.fp:
            raise ValueError(
                "Attempt to write to ZIP archive that was already closed")
        if self._writing:
            raise ValueError(
                "Can't write to ZIP archive while an open writing handle exists"
            )

        with self._lock:
            self._writing = True
            try:
                _ZipRepacker(**opts).repack(self, removed)
            finally:
                self._writing = False
