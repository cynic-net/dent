Dent Operation Details
======================

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

   The command run in the container will be `tail -f /dev/null`; this
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

