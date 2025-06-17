import os
import sys
import time
import tracemalloc
import unittest
import unittest.mock as mock
from tempfile import TemporaryFile
from test.test_zipfile64 import _PRINT_WORKING_MSG_INTERVAL

import zipremove as zipfile

from .test_zipfile import struct_pack_no_dd_sig

# polyfills
try:
    from test.test_zipfile.test_core import Unseekable, requires_zlib
except ImportError:
    # polyfill for Python < 3.12
    from test.test_zipfile import Unseekable, requires_zlib

ENABLED_RESOURCES = set(os.environ.get("TEST_RESOURCES", "").split(","))

def requires(resource_name):
    return unittest.skipUnless(
        resource_name in ENABLED_RESOURCES,
        f"requires resource: {resource_name!r} (set envvar TEST_RESOURCES)"
    )


@requires('extralargefile')
class TestRepack(unittest.TestCase):
    def setUp(self):
        # Create test data.
        line_gen = ("Test of zipfile line %d." % i for i in range(1000000))
        self.data = '\n'.join(line_gen).encode('ascii')

        # It will contain enough copies of self.data to reach about 8 GiB.
        self.datacount = 8*1024**3 // len(self.data)

        # memory usage should not exceed 10 MiB
        self.allowed_memory = 10*1024**2

    def _write_large_file(self, fh):
        next_time = time.monotonic() + _PRINT_WORKING_MSG_INTERVAL
        for num in range(self.datacount):
            fh.write(self.data)
            # Print still working message since this test can be really slow
            if next_time <= time.monotonic():
                next_time = time.monotonic() + _PRINT_WORKING_MSG_INTERVAL
                print((
                '  writing %d of %d, be patient...' %
                (num, self.datacount)), file=sys.__stdout__)
                sys.__stdout__.flush()

    def test_strip_removed_large_file(self):
        """Should move the physical data of a file positioned after a large
        removed file without causing a memory issue."""
        # Try the temp file.  If we do TESTFN2, then it hogs
        # gigabytes of disk space for the duration of the test.
        with TemporaryFile() as f:
            tracemalloc.start()
            self._test_strip_removed_large_file(f)
            self.assertFalse(f.closed)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertLess(peak, self.allowed_memory)

    def _test_strip_removed_large_file(self, f):
        file = 'file.txt'
        file1 = 'largefile.txt'
        data = b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'
        with zipfile.ZipFile(f, 'w') as zh:
            with zh.open(file1, 'w', force_zip64=True) as fh:
                self._write_large_file(fh)
            zh.writestr(file, data)

        with zipfile.ZipFile(f, 'a') as zh:
            zh.remove(file1)
            zh.repack()
            self.assertIsNone(zh.testzip())

    def test_strip_removed_file_before_large_file(self):
        """Should move the physical data of a large file positioned after a
        removed file without causing a memory issue."""
        # Try the temp file.  If we do TESTFN2, then it hogs
        # gigabytes of disk space for the duration of the test.
        with TemporaryFile() as f:
            tracemalloc.start()
            self._test_strip_removed_file_before_large_file(f)
            self.assertFalse(f.closed)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertLess(peak, self.allowed_memory)

    def _test_strip_removed_file_before_large_file(self, f):
        file = 'file.txt'
        file1 = 'largefile.txt'
        data = b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'
        with zipfile.ZipFile(f, 'w') as zh:
            zh.writestr(file, data)
            with zh.open(file1, 'w', force_zip64=True) as fh:
                self._write_large_file(fh)

        with zipfile.ZipFile(f, 'a') as zh:
            zh.remove(file)
            zh.repack()
            self.assertIsNone(zh.testzip())

    def test_strip_removed_large_file_with_dd(self):
        """Should scan for the data descriptor of a removed large file without
        causing a memory issue."""
        # Try the temp file.  If we do TESTFN2, then it hogs
        # gigabytes of disk space for the duration of the test.
        with TemporaryFile() as f:
            tracemalloc.start()
            self._test_strip_removed_large_file_with_dd(f)
            self.assertFalse(f.closed)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertLess(peak, self.allowed_memory)

    def _test_strip_removed_large_file_with_dd(self, f):
        file = 'file.txt'
        file1 = 'largefile.txt'
        data = b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'
        with zipfile.ZipFile(Unseekable(f), 'w') as zh:
            with zh.open(file1, 'w', force_zip64=True) as fh:
                self._write_large_file(fh)
            zh.writestr(file, data)

        with zipfile.ZipFile(f, 'a') as zh:
            # make sure data descriptor bit is really set (by making zip file unseekable)
            for zi in zh.infolist():
                self.assertTrue(zi.flag_bits & 8, f'data descriptor flag not set: {zi.filename}')

            zh.remove(file1)
            zh.repack()
            self.assertIsNone(zh.testzip())

    def test_strip_removed_large_file_with_dd_no_sig(self):
        """Should scan for the data descriptor (without signature) of a removed
        large file without causing a memory issue."""
        # Try the temp file.  If we do TESTFN2, then it hogs
        # gigabytes of disk space for the duration of the test.
        with TemporaryFile() as f:
            tracemalloc.start()
            self._test_strip_removed_large_file_with_dd_no_sig(f)
            self.assertFalse(f.closed)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertLess(peak, self.allowed_memory)

    def _test_strip_removed_large_file_with_dd_no_sig(self, f):
        # Reduce data to 400 MiB for this test, as it's especially slow...
        self.datacount = 400*1024**2 // len(self.data)

        file = 'file.txt'
        file1 = 'largefile.txt'
        data = b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'
        with mock.patch('zipfile.struct.pack', side_effect=struct_pack_no_dd_sig):
            with zipfile.ZipFile(Unseekable(f), 'w') as zh:
                with zh.open(file1, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)
                zh.writestr(file, data)

        with zipfile.ZipFile(f, 'a') as zh:
            # make sure data descriptor bit is really set (by making zip file unseekable)
            for zi in zh.infolist():
                self.assertTrue(zi.flag_bits & 8, f'data descriptor flag not set: {zi.filename}')

            zh.remove(file1)
            zh.repack()
            self.assertIsNone(zh.testzip())

    @requires_zlib()
    def test_strip_removed_large_file_with_dd_no_sig_by_decompression(self):
        """Should scan for the data descriptor (without signature) of a removed
        large file without causing a memory issue."""
        # Try the temp file.  If we do TESTFN2, then it hogs
        # gigabytes of disk space for the duration of the test.
        with TemporaryFile() as f:
            tracemalloc.start()
            self._test_strip_removed_large_file_with_dd_no_sig_by_decompression(
                f, zipfile.ZIP_DEFLATED)
            self.assertFalse(f.closed)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertLess(peak, self.allowed_memory)

    def _test_strip_removed_large_file_with_dd_no_sig_by_decompression(self, f, method):
        file = 'file.txt'
        file1 = 'largefile.txt'
        data = b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'
        with mock.patch('zipfile.struct.pack', side_effect=struct_pack_no_dd_sig):
            with zipfile.ZipFile(Unseekable(f), 'w', compression=method) as zh:
                with zh.open(file1, 'w', force_zip64=True) as fh:
                    self._write_large_file(fh)
                zh.writestr(file, data)

        with zipfile.ZipFile(f, 'a') as zh:
            # make sure data descriptor bit is really set (by making zip file unseekable)
            for zi in zh.infolist():
                self.assertTrue(zi.flag_bits & 8, f'data descriptor flag not set: {zi.filename}')

            zh.remove(file1)
            zh.repack()
            self.assertIsNone(zh.testzip())

if __name__ == "__main__":
    unittest.main()
