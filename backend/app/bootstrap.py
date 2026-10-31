"""Prepare only application-owned data files, then exec the app without root."""
import logging
import os
from pathlib import Path
import stat
import sys


def runtime_identity():
    uid, gid = int(os.getenv('PUID', '10001')), int(os.getenv('PGID', '10001'))
    if not 0 < uid < 2**31 or not 0 < gid < 2**31:
        raise ValueError('PUID and PGID must be positive non-root IDs')
    return uid, gid


def data_files(directory):
    database = os.getenv('DATABASE_URL', '')
    names = {'secret.key'}
    if not database:
        names.add('invest.db')
    elif database.startswith('sqlite:///'):
        candidate = Path(database[len('sqlite:///'):]).absolute()
        if candidate.parent == directory:
            names.add(candidate.name)
    for name in tuple(names - {'secret.key'}):
        names.update({name+'-wal', name+'-shm', name+'.lock'})
    return names


def prepare_data(uid, gid):
    directory = Path(os.getenv('DATA_DIR', '/data')).absolute()
    # Never change an OS directory or follow a symlink out of an app data volume.
    protected = {'/', '/app', '/tmp', '/etc', '/usr', '/var', '/root', '/home', '/mnt', '/run'}
    resolved = directory.resolve()
    if directory != resolved or str(directory) in protected or directory.is_symlink() or any(
            str(directory) == prefix or str(directory).startswith(prefix+'/')
            for prefix in ('/proc', '/sys', '/dev')):
        raise ValueError('DATA_DIR must be a dedicated application directory')
    directory.mkdir(parents=True, exist_ok=True)
    # Linux descriptors avoid following replaced symlinks during ownership repair.
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with_fd = os.open(directory, flags | os.O_DIRECTORY)
    try:
        info = os.fstat(with_fd)
        if (info.st_uid, info.st_gid) != (uid, gid):
            os.fchown(with_fd, uid, gid)
        os.fchmod(with_fd, stat.S_IMODE(info.st_mode) | 0o700)
        for name in sorted(data_files(directory)):
            try:
                descriptor = os.open(name, flags, dir_fd=with_fd)
            except FileNotFoundError:
                continue
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('Application data file must be a regular file')
                if (info.st_uid, info.st_gid) != (uid, gid):
                    os.fchown(descriptor, uid, gid)
                os.fchmod(descriptor, stat.S_IMODE(info.st_mode) | 0o600)
            finally:
                os.close(descriptor)
    finally:
        os.close(with_fd)


def drop_privileges():
    if getattr(os, 'geteuid', lambda: -1)() == 0:
        uid, gid = runtime_identity()
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
        os.environ['HOME'] = '/home/app' if uid == 10001 else '/tmp'


def main():
    try:
        if os.geteuid() == 0:
            prepare_data(*runtime_identity())
        drop_privileges()
        os.execv(sys.executable, [sys.executable, '-m', 'app.container'])
    except Exception as exc:
        logging.error('container_start_failed: stage=data-volume-initialization error=%s errno=%s; '
                      'check NAS volume ACL/mount mode; initialization needs CHOWN, FOWNER, '
                      'DAC_OVERRIDE, SETUID and SETGID capabilities',
                      type(exc).__name__, getattr(exc, 'errno', None))
        return 1


if __name__ == '__main__':
    sys.exit(main())
