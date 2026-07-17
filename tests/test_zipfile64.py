import os
import sys
import time
import tracemalloc
import unittest
import unittest.mock as mock
from contextlib import contextmanager
from tempfile import TemporaryFile
from test.test_zipfile64 import _PRINT_WORKING_MSG_INTERVAL

import zipremove as zipfile

from .test_zipfile import (
    Unseekable,
    require_patched_repack,
    requires_zlib,
    struct_pack_no_dd_sig,
)


def requires_resource(res):
    if not hasattr(requires_resource, '_resources'):
        requires_resource._resources = set(os.environ.get("TEST_RESOURCES", "").split(","))
    return unittest.skipUnless(
        res in requires_resource._resources,
        f"requires resource {res!r} in envvar TEST_RESOURCES"
    )

@requires_resource('extralargefile')
def setUpModule():
    pass


@require_patched_repack()
class TestRepacker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.largefilename = 'largefile.txt'

        line_gen = ("Test of zipfile line %d." % i for i in range(1000000))
        cls.chunk = '\n'.join(line_gen).encode('ascii')

        # It will contain enough copies of cls.chunk to reach about 4.1 GiB.
        cls.chunkcount = int(4.1*1024**3 / len(cls.chunk))

        cls.filename = 'file.txt'
        cls.lorem = b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'

        # Memory usage should not exceed 10 MiB during repacking.
        # This empirical threshold ensures that the internal processing
        # like signature scanning, compressed block end tracing, and
        # data copying are properly buffered without loading the entire
        # large file into memory.
        cls.allowed_memory = 10*1024**2

    @contextmanager
    def assert_memory_usage(self, threshold):
        tracemalloc.start()
        try:
            yield
        finally:
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        self.assertLess(peak, threshold)

    def _write_large_file(self, fh):
        next_time = time.monotonic() + _PRINT_WORKING_MSG_INTERVAL
        for num in range(self.chunkcount):
            fh.write(self.chunk)
            # Print still working message since this test can be really slow
            if next_time <= time.monotonic():
                next_time = time.monotonic() + _PRINT_WORKING_MSG_INTERVAL
                print((
                '  writing %d of %d, be patient...' %
                (num, self.chunkcount)), file=sys.__stdout__)
                sys.__stdout__.flush()

    def test_strip_removed_large_file(self):
        """Should move the physical data of a file positioned after a large
        removed file without causing a memory issue."""
        with TemporaryFile() as f:
            with zipfile.ZipFile(f, 'w') as zh:
                with zh.open(self.largefilename, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)
                zh.writestr(self.filename, self.lorem)

            with self.assert_memory_usage(self.allowed_memory), \
                 zipfile.ZipFile(f, 'a') as zh:
                zh.remove(self.largefilename)
                zh.repack()
                self.assertIsNone(zh.testzip())

    def test_strip_removed_file_before_large_file(self):
        """Should move the physical data of a large file positioned after a
        removed file without causing a memory issue."""
        with TemporaryFile() as f:
            with zipfile.ZipFile(f, 'w') as zh:
                zh.writestr(self.filename, self.lorem)
                with zh.open(self.largefilename, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)

            with self.assert_memory_usage(self.allowed_memory), \
                 zipfile.ZipFile(f, 'a') as zh:
                zh.remove(self.filename)
                zh.repack()
                self.assertIsNone(zh.testzip())

    def test_strip_removed_large_file_with_dd(self):
        """Should scan for the data descriptor of a removed large file without
        causing a memory issue."""
        with TemporaryFile() as f:
            with zipfile.ZipFile(Unseekable(f), 'w') as zh:
                with zh.open(self.largefilename, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)
                zh.writestr(self.filename, self.lorem)

            with self.assert_memory_usage(self.allowed_memory), \
                 zipfile.ZipFile(f, 'a') as zh:
                zh.remove(self.largefilename)
                zh.repack()
                self.assertIsNone(zh.testzip())

    def test_strip_removed_large_file_with_dd_no_sig(self):
        """Should scan for the unsigned data descriptor of a removed large file
        without causing a memory issue."""
        # Reduce data scale for this test, as it's especially slow...
        self.chunkcount = int(30*1024**2 / len(self.chunk))

        with TemporaryFile() as f:
            with mock.patch('zipfile.struct.pack', side_effect=struct_pack_no_dd_sig), \
                 zipfile.ZipFile(Unseekable(f), 'w') as zh:
                with zh.open(self.largefilename, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)
                zh.writestr(self.filename, self.lorem)

            with self.assert_memory_usage(self.allowed_memory), \
                 zipfile.ZipFile(f, 'a') as zh:
                zh.remove(self.largefilename)
                # strict_descriptor=False to scan the unsigned data descriptor
                # (scanning is disabled under the strict_descriptor=True default)
                zh.repack(strict_descriptor=False)
                self.assertIsNone(zh.testzip())

    @requires_zlib()
    def test_strip_removed_large_file_with_dd_no_sig_by_decompression(self):
        """Should scan for the unsigned data descriptor (via tracing compressed
        block end) of a removed large file without causing a memory issue."""
        with TemporaryFile() as f:
            with mock.patch('zipfile.struct.pack', side_effect=struct_pack_no_dd_sig), \
                 zipfile.ZipFile(Unseekable(f), 'w', compression=zipfile.ZIP_DEFLATED) as zh:
                with zh.open(self.largefilename, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)
                zh.writestr(self.filename, self.lorem)

            with self.assert_memory_usage(self.allowed_memory), \
                 zipfile.ZipFile(f, 'a') as zh:
                zh.remove(self.largefilename)
                # strict_descriptor=False to detect the unsigned data descriptor
                # (scanning is disabled under the strict_descriptor=True default)
                zh.repack(strict_descriptor=False)
                self.assertIsNone(zh.testzip())

    def test_copy(self):
        """Should copy the physical data of a file without causing a memory
        issue."""
        with TemporaryFile() as f:
            with zipfile.ZipFile(f, 'w') as zh:
                with zh.open(self.largefilename, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)

            with self.assert_memory_usage(self.allowed_memory), \
                 zipfile.ZipFile(f, 'a') as zh:
                zh.copy(self.largefilename, self.filename)
                self.assertIsNone(zh.testzip())


if __name__ == "__main__":
    unittest.main()
