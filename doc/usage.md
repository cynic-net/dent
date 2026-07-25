Dent Usage, Options and Configuration
=====================================

Reading the short [§"Operation Overview"][oper-ov] section in
`doc/operation.md` will make this document considerably easier to
understand.

#### Arguments

* `dent [options] CONTAINER_NAME [--] [COMMAND [arg ...]]`

Runs the given _COMMAND_ in container _CONTAINER_NAME_ using `docker
exec -it CONTAINER_NAME` or similar. If you supply any _arg_ values
that start with a hyphen, ensure you use the `--` after the container
name to avoid these being parsed as options to Dent.

_CONTAINER_NAME_ is a container name or ID. An existing container with
that name will always be used if present (it will be started if it's
stopped), otherwise it's the name of the container to be created. If
you share the host with other users, you may want to adopt a container
naming convention to avoid name collisions. Dent currently provides
no support for this; it uses the container name exactly as specified.

The default _COMMAND_ is `bash -l` to give an interactive login shell.
Curently _COMMAND_ is always run directly, without a login
environment. To run a single command in your login environment (e.g.,
to use a shell alias) use `-- bash -lc 'cmd arg ...'`.

The user and initial working directory within the container will be
the same as specified by the `docker run` command; this is specified
by the image if Dent created the container. There is currently no
way to override this.

Notes on `docker exec` options:
- The `-t` option (allocate a pseudo-TTY) will be used only if stdin
  is a terminal. There is currently no way to override this.
- The `-i` option (keep stdin open when detached) is always used;
  there seems to be no reason ever not to use it because Dent
  currently does not support `-d` (detached mode).

#### Options

No container command is run if either of the following two options are
given:
* `-h`, `--help`: Ignore all other arguments and print a usage
  summary.
* `-L`, `--list-base-images`: List base images Dent knows it can use
  to create working interactive images. For somewhat silly reasons,
  this still requires a _CNAME_ argument, which is ignored.

The following options control the behaviour of Dent:
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

  Note also that `-r` can be used _only_ when Dent is creating a new
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
[oper-ov]: ./doc/operation.md#operation-overview
