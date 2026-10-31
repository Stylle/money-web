import os
import stat
from unittest.mock import patch

import pytest
from app.bootstrap import runtime_identity, drop_privileges, prepare_data
from app.container import startup_step, StartupError


def test_runtime_user_cannot_be_root_or_an_invalid_id(monkeypatch):
    for value in ('0', '-1', 'not-a-number', str(2**31)):
        monkeypatch.setenv('PUID', value)
        with pytest.raises(ValueError):
            runtime_identity()
    monkeypatch.setenv('PUID', '1026')
    monkeypatch.setenv('PGID', '100')
    assert runtime_identity() == (1026, 100)


def test_privileges_are_dropped_before_execution(monkeypatch):
    monkeypatch.setenv('PUID', '1026')
    monkeypatch.setenv('PGID', '100')
    with patch('os.geteuid', return_value=0, create=True), \
            patch('os.setgroups', create=True) as groups, \
            patch('os.setgid', create=True) as gid, \
            patch('os.setuid', create=True) as uid:
        drop_privileges()
        groups.assert_called_once_with([])
        gid.assert_called_once_with(100)
        uid.assert_called_once_with(1026)


def test_startup_logs_identify_resource_without_leaking_exception_contents(caplog):
    with pytest.raises(StartupError):
        with startup_step('encryption-key'):
            raise PermissionError(13, 'SECRET_password_and_token', '/private/SECRET')
    assert 'stage=encryption-key' in caplog.text
    assert 'PermissionError' in caplog.text
    assert 'errno=13' in caplog.text
    assert 'SECRET' not in caplog.text


@pytest.mark.skipif(os.name != 'posix', reason='Linux descriptor-based permissions')
def test_data_initialization_is_scoped_and_preserves_file_contents(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.delenv('DATABASE_URL')
    key = tmp_path/'secret.key'
    key.write_bytes(b'original-encryption-key')
    key.chmod(0o400)
    other = tmp_path/'not-application-data'
    other.write_text('untouched')
    other.chmod(0o400)
    prepare_data(os.getuid(), os.getgid())
    assert key.read_bytes() == b'original-encryption-key'
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(other.stat().st_mode) == 0o400


@pytest.mark.skipif(os.name != 'posix', reason='Linux descriptor-based permissions')
def test_symlinks_cannot_redirect_permissions_outside_data(tmp_path, monkeypatch):
    data = tmp_path/'data'
    data.mkdir()
    outside = tmp_path/'outside'
    outside.write_bytes(b'preserve')
    outside.chmod(0o400)
    (data/'secret.key').symlink_to(outside)
    monkeypatch.setenv('DATA_DIR', str(data))
    monkeypatch.delenv('DATABASE_URL')
    with pytest.raises(OSError):
        prepare_data(os.getuid(), os.getgid())
    assert stat.S_IMODE(outside.stat().st_mode) == 0o400
    assert outside.read_bytes() == b'preserve'


@pytest.mark.skipif(os.name != 'posix', reason='Linux descriptor-based permissions')
def test_hard_links_cannot_redirect_ownership(tmp_path, monkeypatch):
    data = tmp_path/'data'
    data.mkdir()
    outside = tmp_path/'outside'
    outside.write_bytes(b'preserve')
    os.link(outside, data/'secret.key')
    monkeypatch.setenv('DATA_DIR', str(data))
    monkeypatch.delenv('DATABASE_URL')
    with pytest.raises(ValueError):
        prepare_data(os.getuid(), os.getgid())


@pytest.mark.skipif(os.name != 'posix', reason='Linux paths')
def test_os_directories_are_not_modified(monkeypatch):
    monkeypatch.setenv('DATA_DIR', '/data/..')
    with pytest.raises(ValueError):
        prepare_data(os.getuid(), os.getgid())
