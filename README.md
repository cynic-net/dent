`dent`: Create and Enter Docker Containers
==========================================

`dent` ("Docker ENTer") starts a new process (by default an
interactive command line) in a Docker container, creating the
container and even an image if necessary.

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

Images and containers are created as necessary. When `dent` creates a
new image from a base image it will add:
- A Unix account with the current user's UID and login name.
- A few important basic packages and some configuration for
  interactive use (see below).
- The latest updates for of all packages.

Images created by `dent` include only a minimal set of the most
essential packages (UTF-8 locales, sudo, etc.), those without which
it's fairly inconvenient to install further packages or do very basic
work. If you frequently need more than this, you should use other
systems for further configuring hosts. (`dent` is of course excellent
help with testing these.)


Use of Docker
-------------

This script calls the `docker` command (which must be in the path) for
all communications with the Docker daemon. Security-minded admins will
not put users into the `docker` group (because this is a less-obvious
way of [giving them full root access][root] on the Docker host) but
instead make users' access explicit by allowing them to `sudo` to
root. `dent` handles this by running `sudo docker` instead of `docker`
if it detects that the current user doesn't have access to the Docker
daemon's socket.

`dent` uses the `docker` command for all interaction with the Docker
daemon. Certain operations are more easily done with the Python Docker
API, but others are not and adding a dependency on the [Docker SDK for
Python][py-docker] only to write significantly more code didn't seem
worthwhile.


Installation
------------

`dent` is can be installed from [PyPI][pi-dent], or intalled or cloned from
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


Operation Overview
------------------

The end result achieved by `dent` is to run a command (by default, a
login shell) as a new process in a running container. There are
several other things that must have already been done before this can
happen; these dependencies are described here in reverse order. `dent`
does not know or care whether dependent steps (e.g., ensuring a
container or image exists) were done by itself or via other means such
as manual `docker` commands run by the user.

1. __Entering a Running Container__

   `dent CNAME` will confirm there is a running container named
   _CNAME_ and execute `docker exec -it CNAME bash -l` or similar,
   starting a new process inside the container. Separating container
   startup (`docker run`) from running further commands in the
   container using `docker exec` simplifies running multiple commands
   in the container at the same time.

   Dent changes `docker exec`'s detach key sequence (which you normally
   would not use when using dent) from the default of `ctrl-p,ctrl-q` to
   `ctrl-@,ctrl-d`. This avoids the annoying "hold" of `ctrl-p` until
   another character is typed. This currently cannot be overridden.

2. __Starting the Container__

   If container _CNAME_ exists but is not running, it must be started
   before `docker exec` can be used. This is done by running `docker
   start CNAME`, which restarts it with the command originally
   supplied to `docker run`. This command must keep the container
   running as long as you want to run commands in it with `docker
   exec`. The container creation logic below handles this;
   user-created containers must ensure that their command doesn't exit
   immediately.

3. __Creating the Container__

   If no container _CNAME_ exists, it must be created with `docker
   run`. To do this, either an existing image name must be supplied
   with `-i IMAGE` or a base image from which to build an image (if
   not already built) must be supplied with `-B BASE_IMAGE`. See below
   for more on this.

   The command run in the container will be `/bin/sleep $((2^30))`; this
   will leave the container "running" but doing nothing. (Any work done
   in the container is done by commands run in part 1 above.)

   Note that the configuration of a container (initial command, bind
   mounts, etc.) is fixed when the container is created; if the container
   is stopped or exits and it later restarted with `docker start CNAME`,
   the configuration will be that set up with the original `docker run`.
   Thus, any `-B`/`--base-image` and `-r`/`--run-opts` command line options
   can have effect only at container creation time.

4. __Creating the Image__

   The name of the image is specified with `-i IMAGE`; if that is not
   supplied a default name and tag is generated based on the base
   image name given to `-B BASE_IMAGE` and the login name of the user
   running `dent`. (The image tag may be overridden with `-t TAG`.) If
   an image with that name does not exist, one will be built with a
   configuration designed for interactive use as the user running `dent`.

   If the given image does exist, the `-R` or `--force-rebuild` flag can
   be used to untag that image and do a full image build, ignoring any
   cached layers. The previous image will remain as an unnamed image if
   any containers exist that were created from it; that image can be
   removed with `docker image prune` after removing those containers.

   For the full details of how `dent` builds and sets up the image,
   see the `DOCKERFILE` and the setup script `SETUP_IMAGE` in the
   `dent` source code. Here we briefly describe its general function.

   1. __Package setup.__ The base image is assumed to have `apt` or `yum`
      available and be configured to connect to a source of packages
      commonly used in interactive sessions. This is tested on some
      common versions of Debian, Ubuntu, CentOS, and Fedora.
      - Install git and etckeeper (on systems with apt).
      - Update the package database
      - Install a minimal set of packages for interactive use: sudo,
        curl, vim, git, etc.

   2. __User setup.__ A user will be created (using `useradd`) with the same
      name, uid and groups as the user running `dent`. Sudo will be
      configured to let this user sudo to root without using a password.
      The image's default user and working directory will be configured
      to this user and her home directory.

   `dent` is not designed to be able to build the above image from any
   type of base image. If you have a base image that doesn't work with
   the setup script, it's probably best just to build by hand an
   appropriate image for creating containers and use it with the `-i
   IMAGE` option. (Ideas for making the setup script more general are
   welcome.)


Usage
-----

This section may not be entirely clear if you've not read the
"Operation Overview" section above.

#### Arguments

* `dent [options] CONTAINER_NAME [--] [COMMAND [arg ...]]`

Runs the given _COMMAND_ in container _CONTAINER_NAME_ using `docker
exec -it CONTAINER_NAME` or similar. If you supply any _arg_ values
that start with a hyphen, ensure you use the `--` after the container
name to avoid these being parsed as options to `dent`.

_CONTAINER_NAME_ is a container name or ID. An existing container with
that name will always be used if present (it will be started if it's
stopped), otherwise it's the name of the container to be created. If
you share the host with other users, you may want to adopt a container
naming convention to avoid name collisions. `dent` currently provides
no support for this; it uses the container name exactly as specified.

The default _COMMAND_ is `bash -l` to give an interactive login shell.
Curently _COMMAND_ is always run directly, without a login
environment. To run a single command in your login environment (e.g.,
to use a shell alias) use `-- bash -lc 'cmd arg ...'`.

The user and initial working directory within the container will be
the same as specified by the `docker run` command; this is specified
by the image if `dent` created the container. There is currently no
way to override this.

Notes on `docker exec` options:
- The `-t` option (allocate a pseudo-TTY) will be used only if stdin
  is a terminal. There is currently no way to override this.
- The `-i` option (keep stdin open when detached) is always used;
  there seems to be no reason ever not to use it because `dent`
  currently does not support `-d` (detached mode).

#### Options

No container command is run if either of the following two options are
given:
* `-h`, `--help`: Ignore all other arguments and print a usage
  summary.
* `-L`, `--list-base-images`: List base images `dent` knows it can use
  to create working interactive images. For somewhat silly reasons,
  this still requires a _CNAME_ argument, which is ignored.

The following options control the behaviour of `dent`:
* `-q, --quiet`: Do not print informational lines indicating what Docker
  image and container actions (remove/build/create) are being taken and use
  `docker build --quiet` when building an image.
* `-n, --dry-run`: For commands that would change or execute Docker images
  or containers (including `rmi`, `build`, `run` and `exec`), just print
  the command to stderr. (Unless you use `-q`, the usual user-oriented
  messages about actions to be taken will still appear on stdout.) Build
  configuration is still created, so `--keep-tmpdir` still works. As well
  as testing, this can also be useful to customize image and container
  creation by printing the command that would be executed and then
  executing it by hand with different options.

The following options control which image is used and building of the
image:
* `-i IMAGE, --image IMAGE`: Name of image from which the container
  will be created, if necessary. Has a default value only if `-b` is
  specified.
* `-t TAG, --tag TAG`: Tag for image if `-i` is not specified. (With
  `-i`, specify the tag with the image name in `name:tag` format.) The
  default tag used by `-B` is the user's login name.
* `-B BASE_IMAGE`, `--base-image BASE_IMAGE`: Base image from which to
  build container image if container image (default name or specified
  with `-i`) does not exist.
* `-R, --force-rebuild`: When building an image, ignore any existing
  layers that would be considered "cached" and reused, rebuilding
  every layer in the `Dockerfile` from scratch. (I.e., use `docker
  build --no-cache`.)

The following optons control container creation:
* `-r RUN_OPT`, `--run-opt RUN_OPT`: Add options to pass to `docker run` at
  container creation. These are _not_ split the way the shell does, so
  `-r "-e FOO=bar"` will not work; it will pass `-e FOO=bar` as a single
  argument rather than two arguments to `docker run`. Instead, use
  `-r -e=FOO=bar`.

  Note also that `-r` can be used _only_ when `dent` is creating a new
  container. If it finds an existing container that it would use, it
  will generate an error explaining that the `-r` option would have
  no effect.

The following options are used mainly for development and debugging:
* `--tmpdir TMPDIR`: The directory to use for the Docker build context
  when building an image. Default is a `mkdtmp` name under `/tmp`.
* `--keep-tmpdir`: If a new image is built from a base image, do not
  remove the temporary directory containing the `Dockerfile` and the
  build context. The name of the directory is printed in a message at
  the start of the build. (This message is not suppressed by `-q`.)



<!-------------------------------------------------------------------->
[tmate]: https://tmate.io/

[py-docker]: https://pypi.org/project/docker/
[root]: https://github.com/0cjs/sedoc/blob/master/docker/security.md#leveraging-docker-for-root-access

[gh-dent]: https://github.com/cynic-net/dent
[pactivate]: https://github.com/cynic-net/pactivate
[pi-dent]: https://pypi.org/project/dent
[pipx]: https://pipx.pypa.io/
