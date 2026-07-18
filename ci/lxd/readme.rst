EDA runner overview
-------------------

GitLab CI runner for the sigma-delta project: xschem, ngspice, magic and
netgen-lvs from Ubuntu noble (same versions as the dev machine), plus the
sky130 PDK installed via ciel, pinned in ``cloud-init.yml`` to the version
recorded in DESIGN.md.

Setup lxd (once per host)::

    sudo apt install qemu-utils
    sudo snap install lxd
    sudo usermod --append --groups lxd $USER
    logout/login and/or 'newgrp lxd'

To create VM::

    cd <local_clone_path>/ci/lxd/
    lxc init ubuntu:24.04 eda-runner --vm --device root,size=40GiB -c limits.cpu=4 -c limits.memory=8GiB
    lxc config set eda-runner cloud-init.user-data - < cloud-init.yml
    lxc start eda-runner

Cloud-init keeps working for several minutes after first boot (the PDK
download alone is ~2 GB). To watch::

    lxc exec eda-runner -- /bin/bash
    tail -f /var/log/syslog

or for gitlab-runner::

    lxc exec eda-runner -- su --shell /bin/bash --login gitlab-runner


To register the runner on gitlab (project runner token from
Settings -> CI/CD -> Runners on gitlab.com/pthomas1/sigma-delta)::

    lxc exec eda-runner -- gitlab-runner register --url https://gitlab.com --token xxx

When asked to 'Enter an executor' use 'shell'.

Verify gitlab-runner is running::

    lxc exec eda-runner -- systemctl status gitlab-runner

then push any commit: the ``report`` job in ``.gitlab-ci.yml`` should run
and attach ``reports/dac_compare.html`` as an artifact.

Notes
-----

- ``PDK_ROOT=/opt/pdk`` is exported via ``/etc/profile.d/pdk.sh`` (login
  shells, which the shell executor uses). Not needed by the tier-1 sims yet,
  but tier-2 netlists will depend on it.
- When the PDK version is bumped on the dev machine, update the ciel hash in
  ``cloud-init.yml`` and DESIGN.md together.

To cleanup::

    lxc list
    lxc stop eda-runner
    lxc delete eda-runner
