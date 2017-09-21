Build ceph-ansible in CBS
=========================

The `run.py` script in this repository runs within Jenkins any time Jenkins
sees a new [ceph-ansible](https://github.com/ceph/ceph-ansible) Git tag.
It creates a new SRPM and builds that in the [CentOS Build System (aka
Koji, "CBS")](http://cbs.centos.org/).

Detailed steps:

* Poll for new ceph-ansible tags in GitHub (internal Jenkins polls every
  hour on the hour. Note the JJB configuration currently lives outside this
  repository, so just imagine this part).

* Ensure the prerequisites tools are installed on the slave system, eg
  the "centos-packager" package must be installed.

* `make srpm`

* Map ceph-ansible versions to CBS build targets. For example, ceph-ansible
  "v3" should be built in the ["jewel" CBS build
  target](http://cbs.centos.org/koji/buildtargetinfo?targetID=197)(We will
  need to tweak these mappings over time as upstream ceph-ansible and ceph
  evolve.)

* Authenticate Jenkins user for CBS.

* `cbs build` this ceph-ansible `.src.rpm` file for the appropriate CBS
  target.

* Tag the build into any additional `-candidate` tags. For example, new
  ceph-ansible v3 builds should be immediately tagged into
  ["-luminous-candidate"](http://cbs.centos.org/koji/taginfo?tagID=1157) after
  they are built in the -jewel build target.

When this is complete, a new ceph-ansible RPM is available in the CBS
`-candidate` target for the Storage SIG.

Authentication
--------------
Jenkins uses the Credentials Binding plugin to copy a [CentOS FAS
certificate](https://accounts.centos.org) to the Jenkins slave. The path
to the certificate is stored in a `CENTOS_CERT` environment variable,
and this script will symlink `~/.centos.cert` to that location.

TODO:
=====

* Upload source to [dist-git](https://github.com/CentOS-Storage-SIG)

* Figure out what to do for building directly from ceph-ansible
  `master`, so TripleO can consume the latest ceph-ansible bits even
  sooner.

* Expand this for more packages (eg. ceph and nfs-ganesha)
