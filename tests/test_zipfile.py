import contextlib
import io
import itertools
import os
import struct
import sys
import unittest
import unittest.mock as mock
import warnings

import zipremove as zipfile

# polyfills
try:
    from test.test_zipfile.test_core import (
        TESTFN,
        Unseekable,
        requires_bz2,
        requires_lzma,
        requires_zlib,
        unlink,
    )
except ImportError:
    # polyfill for Python < 3.12
    from test.test_zipfile import (
        TESTFN,
        Unseekable,
        requires_bz2,
        requires_lzma,
        requires_zlib,
        unlink,
    )

try:
    from test.test_zipfile.test_core import requires_zstd
except ImportError:
    # polyfill for Python < 3.14
    def requires_zstd(reason='requires zstd'):
        return unittest.skip(reason)

def requires_zip64fix(reason='requires Python >= 3.11.4 for zip64 fix (#103861)'):
    return unittest.skipUnless(sys.version_info >= (3, 11, 4), reason)


def ComparableZipInfo(zinfo):
    return (zinfo.filename, zinfo.header_offset, zinfo.compress_size, zinfo.CRC)

_struct_pack = struct.pack

def struct_pack_no_dd_sig(fmt, *values):
    """A mock side_effect for native `struct.pack` to not generate a
    signature for data descriptors."""
    # suppress BytesWarning etc.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if values[0] == zipfile._DD_SIGNATURE:
            return _struct_pack(fmt[:1] + fmt[2:], *values[1:])
    return _struct_pack(fmt, *values)

class RepackHelperMixin:
    """Common helpers for remove and repack."""
    @classmethod
    def _prepare_test_files(cls):
        return [
            ('file0.txt', b'Lorem ipsum dolor sit amet, consectetur adipiscing elit'),
            ('file1.txt', b'Duis aute irure dolor in reprehenderit in voluptate velit esse'),
            ('file2.txt', b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'),
        ]

    @classmethod
    def _prepare_zip_from_test_files(cls, zfname, test_files, force_zip64=False):
        zinfos = []
        with zipfile.ZipFile(zfname, 'w', cls.compression) as zh:
            for file, data in test_files:
                with zh.open(file, 'w', force_zip64=force_zip64) as fh:
                    fh.write(data)
                zinfo = zh.getinfo(file)
                zinfos.append(ComparableZipInfo(zinfo))
        return zinfos

class AbstractCopyTests(RepackHelperMixin):
    @classmethod
    def setUpClass(cls):
        cls.test_files = cls._prepare_test_files()

    def test_copy_by_name(self):
        for i in range(3):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zi_new = ('file.txt', zh.start_dir, *zinfos[i][2:])
                    zh.copy(self.test_files[i][0], 'file.txt')

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [*(zi for j, zi in enumerate(zinfos)), zi_new],
                    )

                    # check NameToInfo cache
                    self.assertEqual(ComparableZipInfo(zh.getinfo('file.txt')), zi_new)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_copy_by_zinfo(self):
        for i in range(3):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zi_new = ('file.txt', zh.start_dir, *zinfos[i][2:])
                    zh.copy(zh.infolist()[i], 'file.txt')

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [*(zi for j, zi in enumerate(zinfos)), zi_new],
                    )

                    # check NameToInfo cache
                    self.assertEqual(ComparableZipInfo(zh.getinfo('file.txt')), zi_new)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_copy_zip64(self):
        for i in range(3):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files, force_zip64=True)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zi_new = ('file.txt', zh.start_dir, *zinfos[i][2:])
                    zh.copy(self.test_files[i][0], 'file.txt')

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [*(zi for j, zi in enumerate(zinfos)), zi_new],
                    )

                    # check NameToInfo cache
                    self.assertEqual(ComparableZipInfo(zh.getinfo('file.txt')), zi_new)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_copy_data_descriptor(self):
        for i in range(3):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                with open(TESTFN, 'wb') as fh:
                    zinfos = self._prepare_zip_from_test_files(Unseekable(fh), self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zi_new = ('file.txt', zh.start_dir, *zinfos[i][2:])
                    zh.copy(self.test_files[i][0], 'file.txt')

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [*(zi for j, zi in enumerate(zinfos)), zi_new],
                    )

                    # check NameToInfo cache
                    self.assertEqual(ComparableZipInfo(zh.getinfo('file.txt')), zi_new)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_copy_target_exist(self):
        for i in (1,):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zi_new = ('file2.txt', zh.start_dir, *zinfos[i][2:])
                    zh.copy(self.test_files[i][0], 'file2.txt')

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [*(zi for j, zi in enumerate(zinfos)), zi_new],
                    )

                    # check NameToInfo cache
                    self.assertEqual(ComparableZipInfo(zh.getinfo('file2.txt')), zi_new)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_copy_closed(self, m_repack):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a') as zh:
            zh.close()
            with self.assertRaises(ValueError):
                zh.copy(self.test_files[0][0], 'file.txt')
        m_repack.assert_not_called()

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_copy_writing(self, m_repack):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a') as zh:
            with zh.open('newfile.txt', 'w'):
                with self.assertRaises(ValueError):
                    zh.copy(self.test_files[0][0], 'file.txt')
        m_repack.assert_not_called()

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_copy_unseekble(self, m_repack):
        with open(TESTFN, 'wb') as fh:
            with zipfile.ZipFile(Unseekable(fh), 'w') as zh:
                for file, data in self.test_files:
                    zh.writestr(file, data)

                with self.assertRaises(io.UnsupportedOperation):
                    zh.copy(zh.infolist()[0], 'file.txt')
        m_repack.assert_not_called()

    def test_copy_mode_w(self):
        with zipfile.ZipFile(TESTFN, 'w') as zh:
            for file, data in self.test_files:
                zh.writestr(file, data)
            zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]

            zi_new = ('file.txt', zh.start_dir, *zinfos[0][2:])
            zh.copy(zh.infolist()[0], 'file.txt')

            # check infolist
            self.assertEqual(
                [ComparableZipInfo(zi) for zi in zh.infolist()],
                [*(zi for j, zi in enumerate(zinfos)), zi_new],
            )

            # check NameToInfo cache
            self.assertEqual(ComparableZipInfo(zh.getinfo('file.txt')), zi_new)
            zh.remove(self.test_files[0][0])

        # make sure the zip file is still valid
        with zipfile.ZipFile(TESTFN) as zh:
            self.assertIsNone(zh.testzip())

    def test_copy_mode_x(self):
        unlink(TESTFN)
        with zipfile.ZipFile(TESTFN, 'x') as zh:
            for file, data in self.test_files:
                zh.writestr(file, data)
            zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]

            zi_new = ('file.txt', zh.start_dir, *zinfos[0][2:])
            zh.copy(zh.infolist()[0], 'file.txt')

            # check infolist
            self.assertEqual(
                [ComparableZipInfo(zi) for zi in zh.infolist()],
                [*(zi for j, zi in enumerate(zinfos)), zi_new],
            )

            # check NameToInfo cache
            self.assertEqual(ComparableZipInfo(zh.getinfo('file.txt')), zi_new)
            zh.remove(self.test_files[0][0])

        # make sure the zip file is still valid
        with zipfile.ZipFile(TESTFN) as zh:
            self.assertIsNone(zh.testzip())

class StoredCopyTests(AbstractCopyTests, unittest.TestCase):
    compression = zipfile.ZIP_STORED

@requires_zlib()
class DeflateCopyTests(AbstractCopyTests, unittest.TestCase):
    compression = zipfile.ZIP_DEFLATED

@requires_bz2()
class Bzip2CopyTests(AbstractCopyTests, unittest.TestCase):
    compression = zipfile.ZIP_BZIP2

@requires_lzma()
class LzmaCopyTests(AbstractCopyTests, unittest.TestCase):
    compression = zipfile.ZIP_LZMA

@requires_zstd()
class ZstdCopyTests(AbstractCopyTests, unittest.TestCase):
    compression = zipfile.ZIP_ZSTANDARD

class AbstractRemoveTests(RepackHelperMixin):
    @classmethod
    def setUpClass(cls):
        cls.test_files = cls._prepare_test_files()

    def tearDown(self):
        unlink(TESTFN)

    def test_remove_by_name(self):
        for i in range(0, 3):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zh.remove(self.test_files[i][0])

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [zi for j, zi in enumerate(zinfos) if j != i],
                    )

                    # check NameToInfo cache
                    with self.assertRaises(KeyError):
                        zh.getinfo(self.test_files[i][0])

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_remove_by_zinfo(self):
        for i in range(0, 3):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zh.remove(zh.infolist()[i])

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [zi for j, zi in enumerate(zinfos) if j != i],
                    )

                    # check NameToInfo cache
                    with self.assertRaises(KeyError):
                        zh.getinfo(self.test_files[i][0])

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_remove_by_name_nonexist(self):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
            with self.assertRaises(KeyError):
                zh.remove('nonexist.txt')

    def test_remove_by_zinfo_nonexist(self):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
            with self.assertRaises(KeyError):
                zh.remove(zipfile.ZipInfo('nonexist.txt'))

    def test_remove_by_name_duplicated(self):
        test_files = [
            ('file.txt', b'Lorem ipsum dolor sit amet, consectetur adipiscing elit'),
            ('file.txt', b'Duis aute irure dolor in reprehenderit in voluptate velit esse'),
            ('file1.txt', b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'),
        ]

        # suppress duplicated name warning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            zinfos = self._prepare_zip_from_test_files(TESTFN, test_files)
            with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                zh.remove('file.txt')

                # check infolist
                self.assertEqual(
                    [ComparableZipInfo(zi) for zi in zh.infolist()],
                    [zinfos[0], zinfos[2]],
                )

                # check NameToInfo cache
                self.assertEqual(
                    ComparableZipInfo(zh.getinfo('file.txt')),
                    zinfos[0],
                )

            # make sure the zip file is still valid
            with zipfile.ZipFile(TESTFN) as zh:
                self.assertIsNone(zh.testzip())

            zinfos = self._prepare_zip_from_test_files(TESTFN, test_files)
            with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                zh.remove('file.txt')
                zh.remove('file.txt')

                # check infolist
                self.assertEqual(
                    [ComparableZipInfo(zi) for zi in zh.infolist()],
                    [zinfos[2]],
                )

                # check NameToInfo cache
                with self.assertRaises(KeyError):
                    zh.getinfo('file.txt')

            # make sure the zip file is still valid
            with zipfile.ZipFile(TESTFN) as zh:
                self.assertIsNone(zh.testzip())

    def test_remove_by_zinfo_duplicated(self):
        test_files = [
            ('file.txt', b'Lorem ipsum dolor sit amet, consectetur adipiscing elit'),
            ('file.txt', b'Duis aute irure dolor in reprehenderit in voluptate velit esse'),
            ('file1.txt', b'Sed ut perspiciatis unde omnis iste natus error sit voluptatem'),
        ]

        # suppress duplicated name warning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            zinfos = self._prepare_zip_from_test_files(TESTFN, test_files)
            with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                zh.remove(zh.infolist()[0])

                # check infolist
                self.assertEqual(
                    [ComparableZipInfo(zi) for zi in zh.infolist()],
                    [zinfos[1], zinfos[2]],
                )

                # check NameToInfo cache
                self.assertEqual(
                    ComparableZipInfo(zh.getinfo('file.txt')),
                    zinfos[1],
                )

            # make sure the zip file is still valid
            with zipfile.ZipFile(TESTFN) as zh:
                self.assertIsNone(zh.testzip())

            zinfos = self._prepare_zip_from_test_files(TESTFN, test_files)
            with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                zh.remove(zh.infolist()[1])

                # check infolist
                self.assertEqual(
                    [ComparableZipInfo(zi) for zi in zh.infolist()],
                    [zinfos[0], zinfos[2]],
                )

                # check NameToInfo cache
                self.assertEqual(
                    ComparableZipInfo(zh.getinfo('file.txt')),
                    zinfos[0],
                )

            # make sure the zip file is still valid
            with zipfile.ZipFile(TESTFN) as zh:
                self.assertIsNone(zh.testzip())

            zinfos = self._prepare_zip_from_test_files(TESTFN, test_files)
            with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                infolist = zh.infolist().copy()
                zh.remove(infolist[0])
                zh.remove(infolist[1])

                # check infolist
                self.assertEqual(
                    [ComparableZipInfo(zi) for zi in zh.infolist()],
                    [zinfos[2]],
                )

                # check NameToInfo cache
                with self.assertRaises(KeyError):
                    zh.getinfo('file.txt')

            # make sure the zip file is still valid
            with zipfile.ZipFile(TESTFN) as zh:
                self.assertIsNone(zh.testzip())

    @requires_zip64fix()
    def test_remove_zip64(self):
        for i in range(0, 3):
            with self.subTest(i=i, filename=self.test_files[i][0]):
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files, force_zip64=True)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zh.remove(zh.infolist()[i])

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [zi for j, zi in enumerate(zinfos) if j != i],
                    )

                    # check NameToInfo cache
                    with self.assertRaises(KeyError):
                        zh.getinfo(self.test_files[i][0])

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_remove_closed(self):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a') as zh:
            zh.close()
            with self.assertRaises(ValueError):
                zh.remove(self.test_files[0][0])

    def test_remove_writing(self):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a') as zh:
            with zh.open('newfile.txt', 'w'):
                with self.assertRaises(ValueError):
                    zh.remove(self.test_files[0][0])

    def test_remove_mode_r(self):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'r') as zh:
            with self.assertRaises(ValueError):
                zh.remove(self.test_files[0][0])

    def test_remove_mode_w(self):
        with zipfile.ZipFile(TESTFN, 'w') as zh:
            for file, data in self.test_files:
                zh.writestr(file, data)
            zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]

            zh.remove(self.test_files[0][0])

            # check infolist
            self.assertEqual(
                [ComparableZipInfo(zi) for zi in zh.infolist()],
                [zinfos[1], zinfos[2]],
            )

            # check NameToInfo cache
            with self.assertRaises(KeyError):
                zh.getinfo(self.test_files[0][0])

        # make sure the zip file is still valid
        with zipfile.ZipFile(TESTFN) as zh:
            self.assertIsNone(zh.testzip())

    def test_remove_mode_x(self):
        with zipfile.ZipFile(TESTFN, 'x') as zh:
            for file, data in self.test_files:
                zh.writestr(file, data)
            zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]

            zh.remove(self.test_files[0][0])

            # check infolist
            self.assertEqual(
                [ComparableZipInfo(zi) for zi in zh.infolist()],
                [zinfos[1], zinfos[2]],
            )

            # check NameToInfo cache
            with self.assertRaises(KeyError):
                zh.getinfo(self.test_files[0][0])

        # make sure the zip file is still valid
        with zipfile.ZipFile(TESTFN) as zh:
            self.assertIsNone(zh.testzip())

class StoredRemoveTests(AbstractRemoveTests, unittest.TestCase):
    compression = zipfile.ZIP_STORED

@requires_zlib()
class DeflateRemoveTests(AbstractRemoveTests, unittest.TestCase):
    compression = zipfile.ZIP_DEFLATED

@requires_bz2()
class Bzip2RemoveTests(AbstractRemoveTests, unittest.TestCase):
    compression = zipfile.ZIP_BZIP2

@requires_lzma()
class LzmaRemoveTests(AbstractRemoveTests, unittest.TestCase):
    compression = zipfile.ZIP_LZMA

@requires_zstd()
class ZstdRemoveTests(AbstractRemoveTests, unittest.TestCase):
    compression = zipfile.ZIP_ZSTANDARD

class AbstractRepackTests(RepackHelperMixin):
    @classmethod
    def setUpClass(cls):
        cls.test_files = cls._prepare_test_files()

    def tearDown(self):
        unlink(TESTFN)

    def test_repack_basic(self):
        """Should remove local file entries for deleted files."""
        ln = len(self.test_files)
        iii = (ii for n in range(1, ln + 1) for ii in itertools.combinations(range(ln), n))
        for ii in iii:
            with self.subTest(remove=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                expected_zinfos = self._prepare_zip_from_test_files(TESTFN, test_files)
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for i in ii:
                        zh.remove(self.test_files[i][0])
                    zh.repack()

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_propagation(self):
        """Should call internal API with adequate parameters."""
        self._prepare_zip_from_test_files(TESTFN, self.test_files)

        with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
            zi = zh.remove(zh.infolist()[0])
            with mock.patch.object(zipfile._ZipRepacker, 'repack') as m_rp:
                zh.repack()
        m_rp.assert_called_once_with(zh, None)

        with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
            zi = zh.remove(zh.infolist()[0])
            with mock.patch.object(zipfile._ZipRepacker, 'repack') as m_rp:
                zh.repack([zi])
        m_rp.assert_called_once_with(zh, [zi])

        with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
            with mock.patch.object(zipfile, '_ZipRepacker') as m_rp:
                zh.repack()
        m_rp.assert_called_once_with()

        with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
            with mock.patch.object(zipfile, '_ZipRepacker') as m_rp:
                zh.repack(strict_descriptor=True, chunk_size=1024)
        m_rp.assert_called_once_with(strict_descriptor=True, chunk_size=1024)

    def test_repack_bytes_before_first_file(self):
        """Should preserve random bytes before the first recorded local file entry."""
        for ii in ([], [0], [0, 1], [0, 1, 2]):
            with self.subTest(remove=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'dummy ')
                    expected_zinfos = self._prepare_zip_from_test_files(fh, test_files)
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'dummy ')
                    self._prepare_zip_from_test_files(fh, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for i in ii:
                        zh.remove(self.test_files[i][0])
                    zh.repack()

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_magic_before_first_file(self):
        """Should preserve random signature bytes not forming a valid file entry
        before the first recorded local file entry."""
        for ii in ([], [0], [0, 1], [0, 1, 2]):
            with self.subTest(remove=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'PK\003\004 ')
                    expected_zinfos = self._prepare_zip_from_test_files(fh, test_files)
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'PK\003\004 ')
                    self._prepare_zip_from_test_files(fh, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for i in ii:
                        zh.remove(self.test_files[i][0])
                    zh.repack()

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_file_entry_before_first_file(self):
        """Should preserve seemingly valid file entries not forming consecutive
        valid file entries until the first recorded local file entry.

        This may happen when a self-extractor contains an uncompressed ZIP
        library. (simulated by writing a ZIP file in this test)
        """
        for ii in ([], [0], [0, 1], [0, 1, 2]):
            with self.subTest(remove=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w') as zh:
                        zh.writestr('file.txt', b'dummy')
                        zh.writestr('file2.txt', b'dummy')
                        zh.writestr('file3.txt', b'dummy')
                    fh.write(b' ')
                    expected_zinfos = self._prepare_zip_from_test_files(fh, test_files)
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w') as zh:
                        zh.writestr('file.txt', b'dummy')
                        zh.writestr('file2.txt', b'dummy')
                        zh.writestr('file3.txt', b'dummy')
                    fh.write(b' ')
                    self._prepare_zip_from_test_files(fh, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for i in ii:
                        zh.remove(self.test_files[i][0])
                    zh.repack()

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_bytes_before_removed_files(self):
        """Should preserve if there are bytes before stale local file entries."""
        for ii in ([1], [1, 2], [2]):
            with self.subTest(remove=ii):
                # calculate the expected results
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                        for i, (file, data) in enumerate(self.test_files):
                            if i == ii[0]:
                                fh.write(b' dummy bytes ')
                                zh.start_dir = fh.tell()
                            zh.writestr(file, data)
                        for i in ii:
                            zh.remove(self.test_files[i][0])
                        expected_zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                        for i, (file, data) in enumerate(self.test_files):
                            if i == ii[0]:
                                fh.write(b' dummy bytes ')
                                zh.start_dir = fh.tell()
                            zh.writestr(file, data)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for i in ii:
                        zh.remove(self.test_files[i][0])
                    zh.repack()

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_bytes_after_removed_files(self):
        """Should keep extra bytes if there are bytes after stale local file entries."""
        for ii in ([1], [1, 2], [2]):
            with self.subTest(remove=ii):
                # calculate the expected results
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                        for i, (file, data) in enumerate(self.test_files):
                            if i not in ii:
                                zh.writestr(file, data)
                            if i == ii[-1]:
                                fh.write(b' dummy bytes ')
                                zh.start_dir = fh.tell()
                        expected_zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                        for i, (file, data) in enumerate(self.test_files):
                            zh.writestr(file, data)
                            if i == ii[-1]:
                                fh.write(b' dummy bytes ')
                                zh.start_dir = fh.tell()
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for i in ii:
                        zh.remove(self.test_files[i][0])
                    zh.repack()

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_bytes_between_removed_files(self):
        """Should strip only local file entries before random bytes."""
        # calculate the expected results
        with open(TESTFN, 'wb') as fh:
            with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                zh.writestr(*self.test_files[0])
                fh.write(b' dummy bytes ')
                zh.start_dir = fh.tell()
                zh.writestr(*self.test_files[2])
                zh.remove(self.test_files[2][0])
                expected_zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]
        expected_size = os.path.getsize(TESTFN)

        # do the removal and check the result
        with open(TESTFN, 'wb') as fh:
            with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                zh.writestr(*self.test_files[0])
                zh.writestr(*self.test_files[1])
                fh.write(b' dummy bytes ')
                zh.start_dir = fh.tell()
                zh.writestr(*self.test_files[2])
        with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
            zh.remove(self.test_files[1][0])
            zh.remove(self.test_files[2][0])
            zh.repack()

            # check infolist
            self.assertEqual(
                [ComparableZipInfo(zi) for zi in zh.infolist()],
                expected_zinfos,
            )

        # check file size
        self.assertEqual(os.path.getsize(TESTFN), expected_size)

        # make sure the zip file is still valid
        with zipfile.ZipFile(TESTFN) as zh:
            self.assertIsNone(zh.testzip())

    def test_repack_prepended_bytes(self):
        for ii in ([], [0], [0, 1], [1], [2]):
            with self.subTest(remove=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                fz = io.BytesIO()
                self._prepare_zip_from_test_files(fz, test_files)
                fz.seek(0)
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'dummy ')
                    fh.write(fz.read())
                with zipfile.ZipFile(TESTFN) as zh:
                    expected_zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                fz = io.BytesIO()
                self._prepare_zip_from_test_files(fz, self.test_files)
                fz.seek(0)
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'dummy ')
                    fh.write(fz.read())
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for i in ii:
                        zh.remove(self.test_files[i][0])
                    zh.repack()

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_overlapping_blocks(self):
        for ii in ([0], [1], [2]):
            with self.subTest(remove=ii):
                self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a') as zh:
                    zh._didModify = True
                    for i in ii:
                        zi = zh.infolist()[i]
                        zi.compress_size += 1
                        zi.file_size += 1

                with zipfile.ZipFile(TESTFN, 'a') as zh:
                    with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                        zh.repack()

    def test_repack_removed_basic(self):
        """Should remove local file entries for provided deleted files."""
        ln = len(self.test_files)
        iii = (ii for n in range(1, ln + 1) for ii in itertools.combinations(range(ln), n))
        for ii in iii:
            with self.subTest(remove=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                expected_zinfos = self._prepare_zip_from_test_files(TESTFN, test_files)
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zinfos = [zh.remove(self.test_files[i][0]) for i in ii]
                    zh.repack(zinfos)

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_removed_partial(self):
        """Should remove local file entries only for provided deleted files."""
        ln = len(self.test_files)
        iii = (ii for n in range(1, ln + 1) for ii in itertools.combinations(range(ln), n))
        for ii in iii:
            with self.subTest(removed=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                self._prepare_zip_from_test_files(TESTFN, test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    for zi in zh.infolist().copy():
                        zh.remove(zi)
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                zinfos = self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zinfos = [zh.remove(self.test_files[i][0]) for i, _ in enumerate(self.test_files)]
                    zh.repack([zinfos[i] for i in ii])

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        [],
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_removed_bytes_between_files(self):
        """Should not remove bytes between local file entries."""
        for ii in ([0], [1], [2]):
            with self.subTest(removed=ii):
                # calculate the expected results
                expected_zinfos = []
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                        for j, (file, data) in enumerate(self.test_files):
                            if j not in ii:
                                zh.writestr(file, data)
                                expected_zinfos.append(ComparableZipInfo(zh.getinfo(file)))
                            fh.write(b' dummy bytes ')
                            zh.start_dir = fh.tell()
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                with open(TESTFN, 'wb') as fh:
                    with zipfile.ZipFile(fh, 'w', self.compression) as zh:
                        for file, data in self.test_files:
                            zh.writestr(file, data)
                            fh.write(b' dummy bytes ')
                            zh.start_dir = fh.tell()
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zinfos = [zh.remove(self.test_files[i][0]) for i in ii]
                    zh.repack(zinfos)

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    def test_repack_removed_bad_header_offset(self):
        """Should raise when provided ZipInfo objects has differing header offset."""
        for ii in ([0], [1], [2]):
            with self.subTest(removed=ii):
                self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a') as zh:
                    zinfos = [zh.remove(self.test_files[i][0]) for i in ii]
                    for zi in zinfos:
                        zi.header_offset += 1
                    with self.assertRaisesRegex(zipfile.BadZipFile, 'Bad magic number for file header'):
                        zh.repack(zinfos)

    def test_repack_removed_bad_header_offset2(self):
        """Should raise when provided ZipInfo objects has differing header offset."""
        for ii in ([1], [2]):
            with self.subTest(removed=ii):
                self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a') as zh:
                    zinfos = [zh.remove(self.test_files[i][0]) for i in ii]
                    for zi in zinfos:
                        zi.header_offset -= 1
                    with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                        zh.repack(zinfos)

    def test_repack_removed_bad_non_removed(self):
        """Should raise when provided ZipInfo objects are not removed."""
        for ii in ([0], [1], [2]):
            with self.subTest(removed=ii):
                self._prepare_zip_from_test_files(TESTFN, self.test_files)
                with zipfile.ZipFile(TESTFN, 'a') as zh:
                    zinfos = [zh.getinfo(self.test_files[i][0]) for i in ii]
                    with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                        zh.repack(zinfos)

    def test_repack_removed_prepended_bytes(self):
        for ii in ([], [0], [0, 1], [1], [2]):
            with self.subTest(remove=ii):
                # calculate the expected results
                test_files = [data for j, data in enumerate(self.test_files) if j not in ii]
                fz = io.BytesIO()
                self._prepare_zip_from_test_files(fz, test_files)
                fz.seek(0)
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'dummy ')
                    fh.write(fz.read())
                with zipfile.ZipFile(TESTFN) as zh:
                    expected_zinfos = [ComparableZipInfo(zi) for zi in zh.infolist()]
                expected_size = os.path.getsize(TESTFN)

                # do the removal and check the result
                fz = io.BytesIO()
                self._prepare_zip_from_test_files(fz, self.test_files)
                fz.seek(0)
                with open(TESTFN, 'wb') as fh:
                    fh.write(b'dummy ')
                    fh.write(fz.read())
                with zipfile.ZipFile(TESTFN, 'a', self.compression) as zh:
                    zinfos = [zh.remove(self.test_files[i][0]) for i in ii]
                    zh.repack(zinfos)

                    # check infolist
                    self.assertEqual(
                        [ComparableZipInfo(zi) for zi in zh.infolist()],
                        expected_zinfos,
                    )

                # check file size
                self.assertEqual(os.path.getsize(TESTFN), expected_size)

                # make sure the zip file is still valid
                with zipfile.ZipFile(TESTFN) as zh:
                    self.assertIsNone(zh.testzip())

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_repack_closed(self, m_repack):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a') as zh:
            zh.close()
            with self.assertRaises(ValueError):
                zh.repack()
        m_repack.assert_not_called()

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_repack_writing(self, m_repack):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'a') as zh:
            with zh.open('newfile.txt', 'w'):
                with self.assertRaises(ValueError):
                    zh.repack()
        m_repack.assert_not_called()

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_repack_mode_r(self, m_repack):
        self._prepare_zip_from_test_files(TESTFN, self.test_files)
        with zipfile.ZipFile(TESTFN, 'r') as zh:
            with self.assertRaises(ValueError):
                zh.repack()
        m_repack.assert_not_called()

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_repack_mode_w(self, m_repack):
        with zipfile.ZipFile(TESTFN, 'w') as zh:
            with self.assertRaises(ValueError):
                zh.repack()
        m_repack.assert_not_called()

    @mock.patch.object(zipfile, '_ZipRepacker')
    def test_repack_mode_x(self, m_repack):
        with zipfile.ZipFile(TESTFN, 'x') as zh:
            with self.assertRaises(ValueError):
                zh.repack()
        m_repack.assert_not_called()

class StoredRepackTests(AbstractRepackTests, unittest.TestCase):
    compression = zipfile.ZIP_STORED

@requires_zlib()
class DeflateRepackTests(AbstractRepackTests, unittest.TestCase):
    compression = zipfile.ZIP_DEFLATED

@requires_bz2()
class Bzip2RepackTests(AbstractRepackTests, unittest.TestCase):
    compression = zipfile.ZIP_BZIP2

@requires_lzma()
class LzmaRepackTests(AbstractRepackTests, unittest.TestCase):
    compression = zipfile.ZIP_LZMA

@requires_zstd()
class ZstdRepackTests(AbstractRepackTests, unittest.TestCase):
    compression = zipfile.ZIP_ZSTANDARD

class OtherRepackTests(unittest.TestCase):
    def test_full_overlap_different_names(self):
        # see `test_full_overlap_different_names` in built-in test.test_zipfile
        data = (
            b'PK\x03\x04\x14\x00\x00\x00\x08\x00\xa0lH\x05\xe2\x1e'
            b'8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00b\xed'
            b'\xc0\x81\x08\x00\x00\x00\xc00\xd6\xfbK\\d\x0b`P'
            b'K\x01\x02\x14\x00\x14\x00\x00\x00\x08\x00\xa0lH\x05\xe2'
            b'\x1e8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00aPK'
            b'\x01\x02\x14\x00\x14\x00\x00\x00\x08\x00\xa0lH\x05\xe2\x1e'
            b'8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00bPK\x05'
            b'\x06\x00\x00\x00\x00\x02\x00\x02\x00^\x00\x00\x00/\x00\x00'
            b'\x00\x00\x00'
        )

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack()

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            zi = zh.remove('a')
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack([zi])

        # local entry of 'a' should not be stripped (not found)
        fz = io.BytesIO(data)
        with zipfile.ZipFile(fz, 'a') as zh:
            zh.remove('a')
            zh.repack()

        expected = (
            b'PK\x03\x04\x14\x00\x00\x00\x08\x00\xa0lH\x05\xe2\x1e'
            b'8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00b\xed'
            b'\xc0\x81\x08\x00\x00\x00\xc00\xd6\xfbK\\d\x0b`P'
            b'K\x01\x02\x14\x00\x14\x00\x00\x00\x08\x00\xa0lH\x05\xe2'
            b'\x1e8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00b'
            b'PK\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00/\x00\x00\x00/\x00'
            b'\x00\x00\x00\x00'
        )
        fz.seek(0)
        self.assertEqual(fz.read(), expected)

    def test_quoted_overlap(self):
        # see `test_quoted_overlap` in built-in test.test_zipfile
        data = (
            b'PK\x03\x04\x14\x00\x00\x00\x08\x00\xa0lH\x05Y\xfc'
            b'8\x044\x00\x00\x00(\x04\x00\x00\x01\x00\x00\x00a\x00'
            b'\x1f\x00\xe0\xffPK\x03\x04\x14\x00\x00\x00\x08\x00\xa0l'
            b'H\x05\xe2\x1e8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00'
            b'\x00\x00b\xed\xc0\x81\x08\x00\x00\x00\xc00\xd6\xfbK\\'
            b'd\x0b`PK\x01\x02\x14\x00\x14\x00\x00\x00\x08\x00\xa0'
            b'lH\x05Y\xfc8\x044\x00\x00\x00(\x04\x00\x00\x01'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00aPK\x01\x02\x14\x00\x14\x00\x00\x00\x08\x00\xa0l'
            b'H\x05\xe2\x1e8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00$\x00\x00\x00'
            b'bPK\x05\x06\x00\x00\x00\x00\x02\x00\x02\x00^\x00\x00'
            b'\x00S\x00\x00\x00\x00\x00'
        )

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack()

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            zi = zh.remove('a')
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack([zi])

        # local entry of 'a' should not be stripped (no valid entry)
        fz = io.BytesIO(data)
        with zipfile.ZipFile(fz, 'a') as zh:
            zh.remove('a')
            zh.repack()

        expected = (
            b'PK\x03\x04\x14\x00\x00\x00\x08\x00\xa0lH\x05Y\xfc'
            b'8\x044\x00\x00\x00(\x04\x00\x00\x01\x00\x00\x00a\x00'
            b'\x1f\x00\xe0\xffPK\x03\x04\x14\x00\x00\x00\x08\x00\xa0l'
            b'H\x05\xe2\x1e8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00'
            b'\x00\x00b\xed\xc0\x81\x08\x00\x00\x00\xc00\xd6\xfbK\\'
            b'd\x0b`PK\x01\x02\x14\x00\x14\x00\x00\x00\x08\x00\xa0l'
            b'H\x05\xe2\x1e8\xbb\x10\x00\x00\x00\t\x04\x00\x00\x01\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00$\x00\x00\x00'
            b'bPK\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00/\x00\x00'
            b'\x00S\x00\x00\x00\x00\x00'
        )
        fz.seek(0)
        self.assertEqual(fz.read(), expected)

    def test_partial_overlap_at_dd(self):
        # file 'a' has an unsigned data descriptor (whose information isn't
        # consistent with in central directory) that starts at the starting
        # position of file 'b'
        data = (
            b'PK\x03\x04\x14\x00\x08\x00\x00\x00\x00\x00!\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00acontent'
            b'PK\x03\x04\x14\x00\x00\x00\x00\x00\x00\x00!\x00\xa90\xc5\xfe'
            b'\x07\x00\x00\x00\x07\x00\x00\x00\x01\x00\x00\x00bcontent'
            b'PK\x01\x02\x14\x00\x14\x00\x08\x00\x00\x00\x00\x00!\x00'
            b'\xa90\xc5\xfe\x07\x00\x00\x00\x07\x00\x00\x00\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01\x00\x00\x00\x00a'
            b'PK\x01\x02\x14\x00\x14\x00\x00\x00\x00\x00\x00\x00!\x00'
            b'\xa90\xc5\xfe\x07\x00\x00\x00\x07\x00\x00\x00\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01&\x00\x00\x00b'
            b'PK\x05\x06\x00\x00\x00\x00\x02\x00\x02\x00^\x00\x00\x00L\x00'
            b'\x00\x00\x00\x00'
        )

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            zi = zh.getinfo('a')
            self.assertEqual(zi.header_offset, 0)
            self.assertEqual(zi.compress_size, 7)
            self.assertEqual(zi.file_size, 7)
            self.assertEqual(zi.flag_bits, 8)
            zi = zh.getinfo('b')
            self.assertEqual(zi.header_offset, 38)
            self.assertEqual(zi.compress_size, 7)
            self.assertEqual(zi.file_size, 7)
            self.assertEqual(zi.flag_bits, 0)
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack()

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            zi = zh.remove('a')
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack([zi])

        # local entry of 'a' should not be stripped (no valid entry)
        fz = io.BytesIO(data)
        with zipfile.ZipFile(fz, 'a') as zh:
            zh.remove('a')
            zh.repack()

        expected = (
            b'PK\x03\x04\x14\x00\x08\x00\x00\x00\x00\x00!\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00acontent'
            b'PK\x03\x04\x14\x00\x00\x00\x00\x00\x00\x00!\x00\xa90\xc5\xfe'
            b'\x07\x00\x00\x00\x07\x00\x00\x00\x01\x00\x00\x00bcontent'
            b'PK\x01\x02\x14\x00\x14\x00\x00\x00\x00\x00\x00\x00!\x00'
            b'\xa90\xc5\xfe\x07\x00\x00\x00\x07\x00\x00\x00\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x80\x01&\x00\x00\x00b'
            b'PK\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00/\x00\x00\x00L\x00'
            b'\x00\x00\x00\x00'
        )
        fz.seek(0)
        self.assertEqual(fz.read(), expected)

    def test_overlap_with_central_dir(self):
        # see `test_overlap_with_central_dir` in built-in test.test_zipfile
        data = (
            b'PK\x01\x02\x14\x03\x14\x00\x00\x00\x08\x00G_|Z'
            b'\xe2\x1e8\xbb\x0b\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\xb4\x81\x00\x00\x00\x00aP'
            b'K\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00/\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00'
        )

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Bad magic number for file header'):
                zh.repack()

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            zi = zh.remove('a')
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Bad magic number for file header'):
                zh.repack([zi])

        # local entry of 'a' should not be stripped (not found)
        fz = io.BytesIO(data)
        with zipfile.ZipFile(fz, 'a') as zh:
            zh.remove('a')
            zh.repack()

        expected = (
            b'PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00'
        )
        fz.seek(0)
        self.assertEqual(fz.read(), expected)

    def test_overlap_with_archive_comment(self):
        # see `test_overlap_with_archive_comment` in built-in test.test_zipfile
        data = (
            b'PK\x01\x02\x14\x03\x14\x00\x00\x00\x08\x00G_|Z'
            b'\xe2\x1e8\xbb\x0b\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\xb4\x81E\x00\x00\x00aP'
            b'K\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00/\x00\x00\x00\x00'
            b'\x00\x00\x00*\x00'
            b'PK\x03\x04\x14\x00\x00\x00\x08\x00G_|Z\xe2\x1e'
            b'8\xbb\x0b\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00aK'
            b'L\x1c\x05\xa3`\x14\x8cx\x00\x00'
        )

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack()

        with zipfile.ZipFile(io.BytesIO(data), 'a') as zh:
            zi = zh.remove('a')
            with self.assertRaisesRegex(zipfile.BadZipFile, 'Overlapped entries'):
                zh.repack([zi])

        # local entry of 'a' should not be stripped (not found)
        fz = io.BytesIO(data)
        with zipfile.ZipFile(fz, 'a') as zh:
            zh.remove('a')
            zh.repack()

        expected = (
            b'PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00*\x00'
            b'PK\x03\x04\x14\x00\x00\x00\x08\x00G_|Z\xe2\x1e'
            b'8\xbb\x0b\x00\x00\x00\t\x04\x00\x00\x01\x00\x00\x00aK'
            b'L\x1c\x05\xa3`\x14\x8cx\x00\x00'
        )
        fz.seek(0)
        self.assertEqual(fz.read(), expected)

class ZipRepackerTests(unittest.TestCase):
    def _generate_local_file_entry(self, arcname, raw_bytes,
                                   compression=zipfile.ZIP_STORED,
                                   force_zip64=False, dd=False, dd_sig=True):
        fz = io.BytesIO()
        f = Unseekable(fz) if dd else fz
        cm = (mock.patch.object(struct, 'pack', side_effect=struct_pack_no_dd_sig)
              if not dd_sig else contextlib.nullcontext())
        with zipfile.ZipFile(f, 'w', compression=compression) as zh:
            with cm:
                with zh.open(arcname, 'w', force_zip64=force_zip64) as fh:
                    fh.write(raw_bytes)
            fz.seek(0)
            return fz.read()

    def test_validate_local_file_entry_stored(self):
        self._test_validate_local_file_entry(method=zipfile.ZIP_STORED)

    @requires_zlib()
    def test_validate_local_file_entry_zlib(self):
        self._test_validate_local_file_entry(method=zipfile.ZIP_DEFLATED)

    @requires_bz2()
    def test_validate_local_file_entry_bz2(self):
        self._test_validate_local_file_entry(method=zipfile.ZIP_BZIP2)

    @requires_lzma()
    def test_validate_local_file_entry_lzma(self):
        self._test_validate_local_file_entry(method=zipfile.ZIP_LZMA)

    @requires_zstd()
    def test_validate_local_file_entry_zstd(self):
        self._test_validate_local_file_entry(method=zipfile.ZIP_ZSTANDARD)

    def _test_validate_local_file_entry(self, method):
        repacker = zipfile._ZipRepacker()

        # basic
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        # offset
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_) + 1)
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        bytes_ = b'pre' + bytes_ + b'post'
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 3, len(bytes_) - 4)
        self.assertEqual(result, len(bytes_) - 7)
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 3, len(bytes_))
        self.assertEqual(result, len(bytes_) - 7)
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        # return None if no match at given offset
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 2, len(bytes_) - 4)
        self.assertEqual(result, None)
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 4, len(bytes_) - 4)
        self.assertEqual(result, None)
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        # return None if no sufficient header length
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method)
        bytes_ = bytes_[:29]
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, None)
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        # data descriptor
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method, dd=True)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_called_once_with(fz, 38, len(bytes_), False)
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        # data descriptor (unsigned)
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method, dd=True, dd_sig=False)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_called_once_with(fz, 38, len(bytes_), False)
        m_sddnsbd.assert_called_once_with(fz, 38, len(bytes_), False, method)
        if repacker._scan_data_descriptor_no_sig_by_decompression(fz, 38, len(bytes_), False, method):
            m_sddns.assert_not_called()
        else:
            m_sddns.assert_called_once_with(fz, 38, len(bytes_), False)

        # return None for data descriptor (unsigned) if `strict_descriptor=True`
        repacker = zipfile._ZipRepacker(strict_descriptor=True)
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method, dd=True, dd_sig=False)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, None)
        m_sdd.assert_called_once_with(fz, 38, len(bytes_), False)
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

    @requires_zip64fix()
    def test_validate_local_file_entry_zip64_stored(self):
        self._test_validate_local_file_entry_zip64(method=zipfile.ZIP_STORED)

    @requires_zip64fix()
    @requires_zlib()
    def test_validate_local_file_entry_zip64_zlib(self):
        self._test_validate_local_file_entry_zip64(method=zipfile.ZIP_DEFLATED)

    @requires_zip64fix()
    @requires_bz2()
    def test_validate_local_file_entry_zip64_bz2(self):
        self._test_validate_local_file_entry_zip64(method=zipfile.ZIP_BZIP2)

    @requires_zip64fix()
    @requires_lzma()
    def test_validate_local_file_entry_zip64_lzma(self):
        self._test_validate_local_file_entry_zip64(method=zipfile.ZIP_LZMA)

    @requires_zip64fix()
    @requires_zstd()
    def test_validate_local_file_entry_zip64_zstd(self):
        self._test_validate_local_file_entry_zip64(method=zipfile.ZIP_ZSTANDARD)

    def _test_validate_local_file_entry_zip64(self, method):
        repacker = zipfile._ZipRepacker()

        # zip64
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method, force_zip64=True)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_not_called()
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        # data descriptor + zip64
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method, force_zip64=True, dd=True)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_called_once_with(fz, 58, len(bytes_), True)
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

        # data descriptor (unsigned) + zip64
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method, force_zip64=True, dd=True, dd_sig=False)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_called_once_with(fz, 58, len(bytes_), True)
        m_sddnsbd.assert_called_once_with(fz, 58, len(bytes_), True, method)
        if repacker._scan_data_descriptor_no_sig_by_decompression(fz, 58, len(bytes_), True, method):
            m_sddns.assert_not_called()
        else:
            m_sddns.assert_called_once_with(fz, 58, len(bytes_), True)

        # return None for data descriptor (unsigned) if `strict_descriptor=True`
        repacker = zipfile._ZipRepacker(strict_descriptor=True)
        bytes_ = self._generate_local_file_entry(
            'file.txt', b'dummy', compression=method, force_zip64=True, dd=True, dd_sig=False)
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, None)
        m_sdd.assert_called_once_with(fz, 58, len(bytes_), True)
        m_sddnsbd.assert_not_called()
        m_sddns.assert_not_called()

    def test_validate_local_file_entry_encrypted(self):
        repacker = zipfile._ZipRepacker()

        bytes_ = (
            b'PK\x03\x04'
            b'\x14\x00'
            b'\x09\x00'
            b'\x08\x00'
            b'\xAB\x28'
            b'\xD2\x5A'
            b'\x00\x00\x00\x00'
            b'\x00\x00\x00\x00'
            b'\x00\x00\x00\x00'
            b'\x08\x00'
            b'\x00\x00'
            b'file.txt'
            b'\x97\xF1\x83\x34\x9D\xC4\x8C\xD3\xED\x79\x8C\xA2\xBB\x49\xFF\x1B\x89'
            b'\x3F\xF2\xF4\x4F'
            b'\x11\x00\x00\x00'
            b'\x05\x00\x00\x00'
        )
        fz = io.BytesIO(bytes_)
        with mock.patch.object(repacker, '_scan_data_descriptor',
                               wraps=repacker._scan_data_descriptor) as m_sdd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig_by_decompression',
                               wraps=repacker._scan_data_descriptor_no_sig_by_decompression) as m_sddnsbd, \
             mock.patch.object(repacker, '_scan_data_descriptor_no_sig',
                               wraps=repacker._scan_data_descriptor_no_sig) as m_sddns:
            result = repacker._validate_local_file_entry(fz, 0, len(bytes_))
        self.assertEqual(result, len(bytes_))
        m_sdd.assert_called_once_with(fz, 38, len(bytes_), False)
        m_sddnsbd.assert_not_called()
        m_sddns.assert_called_once_with(fz, 38, len(bytes_), False)

    def test_iter_scan_signature(self):
        bytes_ = b'sig__sig__sig__sig'
        ln = len(bytes_)
        fp = io.BytesIO(bytes_)
        repacker = zipfile._ZipRepacker()

        # basic
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 0, ln)),
            [0, 5, 10, 15],
        )

        # start_offset
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 1, ln)),
            [5, 10, 15],
        )
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 6, ln)),
            [10, 15],
        )
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 16, ln)),
            [],
        )

        # end_offset
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 0, ln - 1)),
            [0, 5, 10],
        )
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 0, ln - 6)),
            [0, 5],
        )

        # chunk_size
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 0, ln, 3)),
            [0, 5, 10, 15],
        )
        self.assertEqual(
            list(repacker._iter_scan_signature(fp, b'sig', 0, ln, 1)),
            [0, 5, 10, 15],
        )

    def test_scan_data_descriptor(self):
        repacker = zipfile._ZipRepacker()

        sig = zipfile._DD_SIGNATURE
        raw_bytes = comp_bytes = b'dummy'
        raw_len = comp_len = len(raw_bytes)
        raw_crc = zipfile.crc32(raw_bytes)

        # basic
        bytes_ = comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            (raw_crc, comp_len, raw_len, 16),
        )

        # return None if no signature
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        # return None if compressed size not match
        bytes_ = comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len + 1, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        bytes_ = comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len - 1, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        bytes_ = b'1' + comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        bytes_ = comp_bytes[1:] + struct.pack('<4L', sig, raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        # zip64
        bytes_ = comp_bytes + struct.pack('<2L2Q', sig, raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), True),
            (raw_crc, comp_len, raw_len, 24),
        )

        # offset
        bytes_ = comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 1, len(bytes_), False),
            None,
        )

        bytes_ = b'123' + comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 3, len(bytes_), False),
            (raw_crc, comp_len, raw_len, 16),
        )

        # end_offset
        bytes_ = comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_) - 1, False),
            None,
        )

        bytes_ = comp_bytes + struct.pack('<4L', sig, raw_crc, comp_len, raw_len) + b'123'
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_) - 3, False),
            (raw_crc, comp_len, raw_len, 16),
        )
        self.assertEqual(
            repacker._scan_data_descriptor(io.BytesIO(bytes_), 0, len(bytes_), False),
            (raw_crc, comp_len, raw_len, 16),
        )

    def test_scan_data_descriptor_no_sig(self):
        repacker = zipfile._ZipRepacker()

        raw_bytes = comp_bytes = b'dummy'
        raw_len = comp_len = len(raw_bytes)
        raw_crc = zipfile.crc32(raw_bytes)

        # basic
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False),
            (raw_crc, comp_len, raw_len, 12),
        )

        # return None if compressed size not match
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len + 1, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len - 1, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        bytes_ = b'1' + comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        bytes_ = comp_bytes[1:] + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False),
            None,
        )

        # zip64
        bytes_ = comp_bytes + struct.pack('<L2Q', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), True),
            (raw_crc, comp_len, raw_len, 20),
        )

        # offset
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 1, len(bytes_), False),
            None,
        )

        bytes_ = b'123' + comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 3, len(bytes_), False),
            (raw_crc, comp_len, raw_len, 12),
        )

        # end_offset
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_) - 1, False),
            None,
        )

        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len) + b'123'
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_) - 3, False),
            (raw_crc, comp_len, raw_len, 12),
        )
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False),
            (raw_crc, comp_len, raw_len, 12),
        )

        # chunk_size
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False, 12),
            (raw_crc, comp_len, raw_len, 12),
        )
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig(io.BytesIO(bytes_), 0, len(bytes_), False, 1),
            (raw_crc, comp_len, raw_len, 12),
        )

    def test_scan_data_descriptor_no_sig_by_decompression_stored(self):
        self._test_scan_data_descriptor_no_sig_by_decompression_invalid(zipfile.ZIP_STORED)

    @requires_zlib()
    def test_scan_data_descriptor_no_sig_by_decompression_zlib(self):
        self._test_scan_data_descriptor_no_sig_by_decompression(zipfile.ZIP_DEFLATED)

    @requires_bz2()
    def test_scan_data_descriptor_no_sig_by_decompression_bz2(self):
        self._test_scan_data_descriptor_no_sig_by_decompression(zipfile.ZIP_BZIP2)

    @requires_lzma()
    def test_scan_data_descriptor_no_sig_by_decompression_lzma(self):
        self._test_scan_data_descriptor_no_sig_by_decompression(zipfile.ZIP_LZMA)

    @requires_zstd()
    def test_scan_data_descriptor_no_sig_by_decompression_zstd(self):
        self._test_scan_data_descriptor_no_sig_by_decompression(zipfile.ZIP_ZSTANDARD)

    def test_scan_data_descriptor_no_sig_by_decompression_unknown(self):
        method = 1024  # simulate an unknown method
        self._test_scan_data_descriptor_no_sig_by_decompression_invalid(method)

    def _test_scan_data_descriptor_no_sig_by_decompression(self, method):
        repacker = zipfile._ZipRepacker()

        raw_bytes = b'dummy'
        raw_len = len(raw_bytes)
        raw_crc = zipfile.crc32(raw_bytes)

        compressor = zipfile._get_compressor(method)
        comp_bytes = compressor.compress(raw_bytes)
        comp_bytes += compressor.flush()
        comp_len = len(comp_bytes)

        # basic
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_), False, method),
            (raw_crc, comp_len, raw_len, 12),
        )

        # return None if data length < DD signature
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, 11, False, method),
            None,
        )

        # return None if compressed size not match
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len + 1, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_), False, method),
            None,
        )

        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len - 1, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_), False, method),
            None,
        )

        # zip64
        bytes_ = comp_bytes + struct.pack('<L2Q', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_), True, method),
            (raw_crc, comp_len, raw_len, 20),
        )

        # offset
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 1, len(bytes_), False, method),
            None,
        )

        bytes_ = b'123' + comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 3, len(bytes_), False, method),
            (raw_crc, comp_len, raw_len, 12),
        )

        # end_offset
        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len)
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_) - 1, False, method),
            None,
        )

        bytes_ = comp_bytes + struct.pack('<3L', raw_crc, comp_len, raw_len) + b'123'
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_) - 3, False, method),
            (raw_crc, comp_len, raw_len, 12),
        )
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_), False, method),
            (raw_crc, comp_len, raw_len, 12),
        )

    def _test_scan_data_descriptor_no_sig_by_decompression_invalid(self, method):
        repacker = zipfile._ZipRepacker()

        bytes_ = b'dummy'
        self.assertEqual(
            repacker._scan_data_descriptor_no_sig_by_decompression(
                io.BytesIO(bytes_), 0, len(bytes_), False, method),
            False,
        )

    @requires_zlib()
    def test_trace_compressed_block_end_zlib(self):
        import zlib
        self._test_trace_compressed_block_end(zipfile.ZIP_DEFLATED, zlib.error)

    @requires_bz2()
    def test_trace_compressed_block_end_bz2(self):
        self._test_trace_compressed_block_end(zipfile.ZIP_BZIP2, OSError)

    @requires_zstd()
    def test_trace_compressed_block_end_zstd(self):
        import compression.zstd
        self._test_trace_compressed_block_end(zipfile.ZIP_ZSTANDARD, compression.zstd.ZstdError)

    def _test_trace_compressed_block_end(self, method, exc_cls):
        repacker = zipfile._ZipRepacker()

        compressor = zipfile._get_compressor(method)

        comp_bytes = compressor.compress(b'dummy')
        comp_bytes += compressor.flush()
        comp_len = len(comp_bytes)

        # basic
        decompressor = zipfile._get_decompressor(method)
        bytes_ = comp_bytes
        self.assertEqual(
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 0, len(bytes_), decompressor),
            comp_len,
        )

        # offset
        decompressor = zipfile._get_decompressor(method)
        bytes_ = comp_bytes
        with self.assertRaises(exc_cls):
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 1, len(bytes_), decompressor)

        decompressor = zipfile._get_decompressor(method)
        bytes_ = b'123' + comp_bytes
        with self.assertRaises(exc_cls):
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 0, len(bytes_), decompressor)

        decompressor = zipfile._get_decompressor(method)
        bytes_ = b'123' + comp_bytes
        self.assertEqual(
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 3, len(bytes_), decompressor),
            comp_len + 3,
        )

        # end_offset
        decompressor = zipfile._get_decompressor(method)
        bytes_ = comp_bytes
        with self.assertRaises(EOFError):
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 0, len(bytes_) - 1, decompressor)

        decompressor = zipfile._get_decompressor(method)
        bytes_ = comp_bytes + b'123'
        self.assertEqual(
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 0, len(bytes_) - 3, decompressor),
            comp_len,
        )

        # chunk_size
        decompressor = zipfile._get_decompressor(method)
        bytes_ = comp_bytes
        self.assertEqual(
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 0, len(bytes_), decompressor, 16),
            comp_len,
        )

        decompressor = zipfile._get_decompressor(method)
        bytes_ = comp_bytes
        self.assertEqual(
            repacker._trace_compressed_block_end(io.BytesIO(bytes_), 0, len(bytes_), decompressor, 1),
            comp_len,
        )

    def test_copy_bytes(self):
        repacker = zipfile._ZipRepacker()

        fp = io.BytesIO(b'abc123')
        repacker._copy_bytes(fp, 0, 3, 3)
        self.assertEqual(fp.getvalue(), b'abcabc')

        fp = io.BytesIO(b'abc123')
        repacker._copy_bytes(fp, 3, 0, 3)
        self.assertEqual(fp.getvalue(), b'123123')

        fp = io.BytesIO(b'abc123')
        repacker._copy_bytes(fp, 0, 4, 3)
        self.assertEqual(fp.getvalue(), b'abc1abc')

        fp = io.BytesIO(b'abc123')
        repacker._copy_bytes(fp, 0, 10, 3)
        self.assertEqual(fp.getvalue(), b'abc123\x00\x00\x00\x00abc')

        fp = io.BytesIO(b'abc123')
        repacker._copy_bytes(fp, 0, 3, 2)
        self.assertEqual(fp.getvalue(), b'abcab3')

        # check chunk_size
        repacker = zipfile._ZipRepacker(chunk_size=6)
        fp = io.BytesIO(b'abcdef123456')
        with mock.patch.object(fp, 'read', wraps=fp.read) as m_read:
            repacker._copy_bytes(fp, 0, 12, 6)
        self.assertEqual(fp.getvalue(), b'abcdef123456abcdef')
        m_read.assert_called_once_with(6)

        repacker = zipfile._ZipRepacker(chunk_size=3)
        fp = io.BytesIO(b'abcdef123456')
        with mock.patch.object(fp, 'read', wraps=fp.read) as m_read:
            repacker._copy_bytes(fp, 0, 12, 6)
        self.assertEqual(fp.getvalue(), b'abcdef123456abcdef')
        self.assertEqual(m_read.mock_calls, [mock.call(3), mock.call(3)])

        repacker = zipfile._ZipRepacker(chunk_size=1)
        fp = io.BytesIO(b'abcdef123456')
        with mock.patch.object(fp, 'read', wraps=fp.read) as m_read:
            repacker._copy_bytes(fp, 0, 12, 6)
        self.assertEqual(fp.getvalue(), b'abcdef123456abcdef')
        self.assertEqual(m_read.mock_calls, [
            mock.call(1), mock.call(1), mock.call(1), mock.call(1), mock.call(1), mock.call(1)])

if __name__ == "__main__":
    unittest.main()
