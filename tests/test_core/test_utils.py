"""Tests for bactopia.utils."""

import pytest

from bactopia.utils import (
    chunk_list,
    file_exists,
    is_local,
    mkdir,
    prefix_keys,
    remove_keys,
    validate_file,
)


class TestValidateFile:
    def test_exists(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = validate_file(str(f))
        assert result == f.resolve()

    def test_missing(self):
        with pytest.raises(FileNotFoundError):
            validate_file("/nonexistent/file.txt")


class TestPrefixKeys:
    def test_basic(self):
        result = prefix_keys({"a": 1, "b": 2}, "pre")
        assert result == {"pre_a": 1, "pre_b": 2}

    def test_empty(self):
        assert prefix_keys({}, "pre") == {}


class TestRemoveKeys:
    def test_basic(self):
        result = remove_keys({"a": 1, "b": 2, "c": 3}, ["b"])
        assert result == {"a": 1, "c": 3}

    def test_missing_key_ignored(self):
        result = remove_keys({"a": 1}, ["nonexistent"])
        assert result == {"a": 1}

    def test_empty(self):
        assert remove_keys({}, ["a"]) == {}


class TestFileExists:
    def test_true(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert file_exists(str(f)) is True

    def test_false(self):
        assert file_exists("/nonexistent/file.txt") is False


class TestIsLocal:
    def test_local_path(self):
        assert is_local("/home/user/file.txt") is True

    def test_s3(self):
        assert is_local("s3://bucket/file.txt") is False

    def test_gs(self):
        assert is_local("gs://bucket/file.txt") is False

    def test_az(self):
        assert is_local("az://container/file.txt") is False

    def test_https(self):
        assert is_local("https://example.com/file.txt") is False


class TestChunkList:
    def test_even_chunks(self):
        result = list(chunk_list([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_uneven_chunks(self):
        result = list(chunk_list([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_single_chunk(self):
        result = list(chunk_list([1, 2, 3], 10))
        assert result == [[1, 2, 3]]

    def test_empty(self):
        result = list(chunk_list([], 5))
        assert result == []


class TestMkdir:
    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "subdir" / "nested"
        result = mkdir(str(new_dir))
        assert new_dir.exists()
        assert result == new_dir

    def test_existing_directory(self, tmp_path):
        result = mkdir(str(tmp_path))
        assert result == tmp_path


class TestGetPlatform:
    def test_linux(self, mocker):
        mocker.patch("bactopia.utils.platform", "linux")
        from bactopia.utils import get_platform

        assert get_platform() == "linux"

    def test_mac(self, mocker):
        mocker.patch("bactopia.utils.platform", "darwin")
        from bactopia.utils import get_platform

        assert get_platform() == "mac"

    def test_windows_exits(self, mocker):
        mocker.patch("bactopia.utils.platform", "win32")
        from bactopia.utils import get_platform

        with pytest.raises(SystemExit):
            get_platform()
