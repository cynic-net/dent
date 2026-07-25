Dent: Create and Enter Docker Containers
========================================

Dent ("Docker ENTer") starts a new process (by default an interactive
command line) running as you (not `root`) in a Docker container, if
necessary creating the container and even an image with your $HOME etc. all
set up.

One use of this is simply to start one or more command lines (or run
commands) in an existing container or a new container based on an
arbitrary image. This can be used to debug an application running in a
container or explore the contents of a container or image.

Another use is to create and start containers designed to be
persistent (kept and reused for some time) and used for interactive
work at a shell prompt as a regular (non-root) user. Containers like
this are useful for:
- Development and testing of techniques, scripts and applications
  under different Linux distributions and versions.
- Testing system setup and other sysadmin tools.
- Providing a safe environment for sharing terminals with [tmate] or
  similar programs, where you don't want others to have access to
  files in your account, SSH keys in agents, and possibly root access
  to your host.
- Providing a sandboxed environment for agents such as Claude Code that
  have a tendency to reach out and do things to your system (even via sudo)
  and other systems if they find your keys.

Images and containers are created as necessary. When Dent creates a
new image from a base image it will add:
- A Unix account with the current user's UID and login name.
- A few important basic packages and some configuration for
  interactive use (see below).
- The latest updates for of all packages.

Images created by Dent include only a minimal set of the most
essential packages (UTF-8 locales, sudo, etc.), those without which
it's fairly inconvenient to install further packages or do very basic
work. If you frequently need more than this, you should use other
systems for further configuring hosts. (Dent is of course excellent
help with testing these.)

The following further documentation is available:

* [Installation](#installation) (below)
* [Operation][oper]
* [Usage, Options and Configuration](./doc/usage.md)


Installation
------------

Dent can be installed from [PyPI][pi-dent], or intalled or cloned from
[GitHub][gh-dent].

Basic install:

    pip install dent
    dent --help

Using [pactivate]'s `pae`:

    pae -c dent dent
    pae dent --help

Using [pipx]:

    pipx run dent --help

From GitHub:

    pip install dent@git+https://github.com/cynic-net/dent@refs/heads/dev/cjs/24h05/pypi-package
    dent --help



<!-------------------------------------------------------------------->
[tmate]: https://tmate.io/

[oper]: ./doc/operation.md
[oper-ov]: ./doc/operation.md#operation-overview

[gh-dent]: https://github.com/cynic-net/dent
[pactivate]: https://github.com/cynic-net/pactivate
[pi-dent]: https://pypi.org/project/dent
[pipx]: https://pipx.pypa.io/

