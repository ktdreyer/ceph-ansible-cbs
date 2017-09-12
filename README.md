Intended steps:
===============

* Poll for new ceph-ansible tag in GitHub
  node: `CentOS-7-x86_64-GenericCloud-released-latest`

* `make srpm`

* Map ceph-ansible versions to CBS tags, eg "v3" should go into "luminous".

* (Authenticate Jenkins user for CBS - how?)

* `cbs build target ceph-ansible...src.rpm`

* Upload source to dist-git
