Intended steps:
===============

* Poll for new ceph-ansible tag in GitHub

* `make srpm`

* Map ceph-ansible versions to CBS tags, eg "v3" should go into "luminous".

* (Authenticate Jenkins user for CBS - how?)

* `cbs build --target=target... ceph-ansible...src.rpm` (need exact parameters here)
