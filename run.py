#!/usr/bin/python

import errno
import grp
from glob import glob
import os
import re
import subprocess
import sys
import shutil
import tempfile
import requests


# Intended to run in Jenkins after every new Git tag.

# Possible YAML layout for all our packages:
# (need to see how this compares with rdoinfo)
# (also this is ok for only el7, but we need to split this out for el7+el8)
#   ceph-ansible:
#     versions:
#       r'v2':
#         target: None
#       r'v':
#         target: storage7-ceph-jewel-el7
#         tags:
#          - storage7-ceph-luminous-candidate

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
    cmd = ['cbs', 'build', '--wait', target, srpm]
    if scratch:
        cmd += ['--scratch']
    subprocess.check_call(cmd)
    return srpm_nvr(srpm)


def get_cbs_target(version):
    """
    Return a CBS build target for this ceph-ansible version.

    :param version: a ceph-ansible Git tag, eg. "v3.0.0rc7"
    :returns: ``str``, eg "storage7-ceph-jewel-el7", or None if we should not
               build this tag.
    """
    version = re.sub('^v', '', version)
    if version.startswith('3.0.'):
        return 'storage7-ceph-jewel-el7'
    if version.startswith('3.1.'):
        return 'storage7-ceph-mimic-el7'
    if version.startswith('3.2.'):
        return 'storage7-ceph-mimic-el7'
    return None


def get_needed_cbs_tags(version):
    """
    Return all the CBS tags that should have this ceph-ansible version.

    :param version: a ceph-ansible Git tag, eg. "v3.0.0rc7"
    :returns: ``list`` of ``str``, eg ["storage7-ceph-jewel-candidate"]
    """
    version = re.sub('^v', '', version)
    releases = []
    if version.startswith('3.0.'):
        releases = ['jewel', 'luminous']
    if version.startswith('3.1.'):
        releases = ['luminous', 'mimic']
    if version.startswith('3.2.'):
        releases = ['luminous', 'mimic']
    return ['storage7-ceph-%s-candidate' % release for release in releases]


def get_cbs_tag_list(nvr):
    """
    Return all the CBS tags for this build.

    :param nvr: a build Name-Version-Release that has been built.
    :returns: ``list`` of ``str``, eg ["storage7-ceph-jewel-candidate"]
    """
    import koji
    conf = koji.read_config('cbs')
    hub = conf['server']
    print('searching %s for %s tags' % (hub, nvr))
    session = koji.ClientSession(hub, {})
    tags = session.listTags(nvr)
    return [tag['name'] for tag in tags]


def tag_build(nvr, tag):
    """
    Tag this build NVR into this CBS tag.

    :param nvr: a build Name-Version-Release, for example
                "ceph-ansible-3.0.0-0.1.rc10.1.el7"
    :param tag: a CBS tag, eg "storage7-ceph-luminous-candidate"
    """
    cmd = ['cbs', 'tag', tag, nvr]
    subprocess.check_call(cmd)


def srpm_nvr(srpm):
    """
    Return the build NVR from this SRPM file.

    :param version: a SRPM file, eg. ceph-ansible-3.0.0-0.1.rc10.1.el7.src.rpm
    :returns: ``str``, eg. ceph-ansible-3.0.0-0.1.rc10.1.el7
    """
    filename = os.path.basename(srpm)
    if not filename.endswith('.src.rpm'):
        raise ValueError('%s does not look like a SRPM' % filename)
    return filename[:-8]


def get_cbs_build(srpm):
    """
    Return the Name-Version-Release if a build already exists in CBS for this
    SRPM, or None if it does not exist.

    :param version: a SRPM file name,
                    eg. ceph-ansible-3.0.0-0.1.rc10.1.el7.src.rpm
    :returns: ``str``, eg. "ceph-ansible-3.0.0-0.1.rc10.1.el7"
               if the completed build exists in CBS.
               ``None`` if the completed build does not exist in CBS.
    """
    nvr = srpm_nvr(srpm)
    import koji  # oh yeah
    conf = koji.read_config('cbs')
    hub = conf['server']
    print('searching %s for %s' % (hub, nvr))
    session = koji.ClientSession(hub, {})
    build = session.getBuild(nvr)
    if build is None:
        return None
    if koji.BUILD_STATES[build['state']] == 'COMPLETE':
        return nvr
    return None


def hack_three_one_zero():
    """
    Modify the version for a 3.1.0 build.

    Unfortunately "ceph-ansible-3.1.0beta2-1.el7" was pushed live.
    https://bugs.centos.org/view.php?id=14593 To build an RPM with a version
    that will override this, we tack on an extra zero if "Version" is "3.1.0".

    RPM treats a Version of "3.1.0.0" as higher than "3.1.0beta2".

    We can delete this hack after v3.1.1 is tagged in GitHub.
    """
    specfile = 'ceph-ansible.spec'
    with open(specfile) as specfh:
        contents = specfh.read()
    oldv = 'Version:        3.1.0'
    newv = 'Version:        3.1.0.0'
    if oldv not in contents:
        return
    with tempfile.NamedTemporaryFile() as temp:
        newcontents = contents.replace(oldv, newv)
        newcontents = newcontents.replace('%{version}', '3.1.0')
        newcontents = newcontents.replace('%autosetup -p1',
                                          '%autosetup -p1 -n %{name}-3.1.0')
        temp.write(newcontents)
        temp.flush()
        shutil.copyfile(temp.name, specfile)


def make_srpm():
    """ Run "make srpm" and return the filename of the resulting .src.rpm. """
    cmd = ['make', 'srpm']
    # Workaround the incompat between fedpkg and centos-packager
    # (needs to go into ceph-ansible Makefile upstream..)
    subprocess.check_call(['make', 'dist', 'spec'])
    subprocess.check_call(['make', 'spec'])
    # Delete this hack after v3.1.1 is tagged in GitHub:
    hack_three_one_zero()
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


if __name__ == '__main__':
    ensure_prereqs()
    version = get_version()
    srpm = make_srpm()

    target = get_cbs_target(version)
    if not target:
        print('No CBS built target configured for %s. Quitting' % version)
        raise SystemExit()

    nvr = get_cbs_build(srpm)
    if nvr is None:
        nvr = cbs_build(target, srpm)
    else:
        print('%s has already been built in CBS. Skipping build.' % nvr)

    # Tag this build into any additional desired CBS tags
    needed_tags = get_needed_cbs_tags(version)
    already_tagged = get_cbs_tag_list(nvr)
    for tag in set(needed_tags) - set(already_tagged):
        print('tagging %s into %s' % (nvr, tag))
        tag_build(nvr, tag)
