from glob import glob
import re
import subprocess


def get_version():
    """ Get a version from "git describe".  """
    cmd = ['git', 'describe', '--tags', '--abbrev=0', '--match "v*"']
    output = subprocess.check_output(cmd)
    # py3 needs to decode output here before returning...
    return output


def cbs_build(target, srpm):
    """
    Build a SRPM in CBS for a target.

    :param target: a CBS target, eg. storage7-ceph-jewel-el7
    :param   srpm: path to a .src.rpm file.
    """
    cmd = ['cbs', 'build', target, srpm]
    subprocess.check_call(cmd)


def get_cbs_target(version):
    """
    Return a CBS target for this ceph-ansible version,

    :param version: a ceph-ansible Git tag, eg. "v3.0.0rc7"
    :returns: ``str``, eg "storage7-ceph-jewel-el7"
    """
    version = re.sub('^v', '', version)
    release = 'luminous'
    if version.startswith('2.'):
        release = 'jewel'
    return 'storage7-ceph-%s-el7' % release


def make_srpm():
    """ Run "make srpm" and return the filename of the resulting .src.rpm. """
    cmd = ['cbs', 'build', target, srpm]
    subprocess.check_call(cmd)
    # TODO: cat some logs if that call failed?
    files = glob('ceph-ansible-*.src.rpm')
    if not files:
        raise RuntimeError('could not find any ceph-ansible .src.rpm')
    if len(files) > 1:
        raise RuntimeError('multiple ceph-ansible .src.rpm files found')
    return files[0]


version = get_version()
target = get_cbs_target(version)
srpm = make_srpm()
cbs_build(target, srpm)
