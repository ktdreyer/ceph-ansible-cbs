#!/usr/bin/python

import errno
import grp
from glob import glob
import os
import re
import subprocess
import sys
import requests


# Intended to run in Jenkins after every new Git tag.


def ensure_prereqs():
    """ Ensure everything is set up as expected. """
    # Ensure we are a member of the "mock" Unix group.
    groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]
    if 'mock' not in groups:
        raise RuntimeError('current user not in the "mock" group.')

    # Ensure centos-packager (ie, /usr/bin/cbs) is installed.
    ensure_package('centos-packager')

    ensure_centos_cert()
    ensure_server_ca()

    sys.stdout.flush()

    subprocess.check_call(['centos-cert', '-v'])

    subprocess.check_call(['cbs', 'hello'])


def ensure_centos_cert():
    """ Ensure cbs x509 cert is in place """
    certpath = os.path.expanduser('~/.centos.cert')
    if 'CENTOS_CERT' not in os.environ:
        # Manual testing? don't bother setting up the cert symlink.
        print('CENTOS_CERT env var is not set. Not touching %s' % certpath)
        return
    try:
        os.unlink(certpath)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    centos_cert = os.environ['CENTOS_CERT']
    os.symlink(centos_cert, certpath)


def ensure_server_ca():
    """ Ensure that the CentOS server cert authority is in place. """
    # copied from centos-packager (GPLv3)
    servercapath = os.path.expanduser('~/.centos-server-ca.cert')
    if os.path.exists(servercapath):
        return
    servercaurl = 'https://accounts.centos.org/ca/ca-cert.pem'
    print('downloading %s to %s' % (servercaurl, servercapath))
    with open(servercapath, 'w') as servercacertfile:
        r = requests.get(servercaurl)
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print("""Could not download CA Certificate!
Response Code: {0}
Message: {1}""".format(e.response.status_code, e.response.reason)).strip()
            sys.exit(1)
        response = r.text
        servercacertfile.write(response)


def ensure_package(pkg):
    cmd = ['rpm', '-qv', pkg]
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
        cmd = ['sudo', 'yum', '-y', 'install', pkg]
        subprocess.check_call(cmd)


def get_version():
    """ Get a version from "git describe".  """
    cmd = ['git', 'describe', '--tags', '--abbrev=0', '--match', 'v*']
    try:
        output = subprocess.check_output(cmd)
    except subprocess.CalledProcessError:
        print('failed to find "v" git tags in %s' % os.getcwd())
        raise
    # py3 needs to decode output here before returning...
    return output


def cbs_build(target, srpm, scratch=False):
    """
    Build a SRPM in CBS for a target.

    :param target: a CBS target, eg. storage7-ceph-jewel-el7
    :param   srpm: path to a .src.rpm file.
    """
    cmd = ['cbs', 'build', target, srpm]
    if scratch:
        cmd += ['--scratch']
    subprocess.check_call(cmd)


def get_cbs_target(version):
    """
    Return a CBS build target for this ceph-ansible version,

    :param version: a ceph-ansible Git tag, eg. "v3.0.0rc7"
    :returns: ``str``, eg "storage7-ceph-jewel-el7"
    """
    version = re.sub('^v', '', version)
    release = 'jewel'
    if version.startswith('2.'):
        # too old; do nothing.
        return None
    return 'storage7-ceph-%s-el7' % release


def srpm_nvr(srpm):
    """
    Return the build NVR from this SRPM file.
    # eg. 'ceph-ansible-3.0.0-0.rc10.1.el7'
    :param version: a SRPM file, eg. ceph-ansible-3.0.0-0.1.rc10.1.el7.src.rpm
    :returns: ``str``, ceph-ansible-3.0.0-0.1.rc10.1.el7
    """
    filename = os.path.basename(srpm)
    if not filename.endswith('.src.rpm'):
        raise ValueError('%s does not look like a SRPM' % filename)
    return filename[:7]


def build_exists(srpm):
    """
    Return True if a build already exists in CBS for this SRPM.

    :param version: a SRPM file name,
                    eg. ceph-ansible-3.0.0-0.1.rc10.1.el7.src.rpm
    :returns: ``bool``, True if the build exists
    """
    nvr = srpm_nvr(srpm)
    import koji  # oh yeah
    conf = koji.read_config('cbs')
    hub = conf['server']
    print('searching %s for %s' % (hub, nvr))
    session = koji.ClientSession(hub, {})
    build = session.getBuild(nvr)
    return build is not None


def make_srpm():
    """ Run "make srpm" and return the filename of the resulting .src.rpm. """
    cmd = ['make', 'srpm']
    # Workaround the incompat between fedpkg and centos-packager
    # (needs to go into ceph-ansible Makefile upstream..)
    subprocess.check_call(['make', 'dist', 'spec'])
    subprocess.check_call(['make', 'spec'])
    cmd = ['rpmbuild', '-bs', 'ceph-ansible.spec',
           '--define', '_topdir .',
           '--define', '_sourcedir .',
           '--define', '_srcrpmdir .',
           '--define', 'dist .el7',
           ]
    subprocess.check_call(cmd)
    # TODO: cat some logs if that call failed?
    files = glob('ceph-ansible-*.src.rpm')
    if not files:
        raise RuntimeError('could not find any ceph-ansible .src.rpm')
    if len(files) > 1:
        raise RuntimeError('multiple ceph-ansible .src.rpm files found')
    return files[0]


ensure_prereqs()
version = get_version()
srpm = make_srpm()

if build_exists(srpm):
    print('%s has already been built in CBS. Quitting' % srpm)
    raise SystemExit()

target = get_cbs_target(version)

if not target:
    print('No CBS built target configured for %s. Quitting' % version)
    raise SystemExit()

cbs_build(target, srpm)
