To-do Lists
===========

### General

- CMD is run in login env unless raw option given. (Concatenate
  command/args and pass to `bash -lc`.)
- Add support for `docker exec` options `-u`, `-w`, `-e`, and maybe
  `--no-tty` and/or `-d`.
- Create image from container.
- Special tmate support because tmate needs a private key.
- Support for detach and setting user, CWD, env vars with `docker exec`.
- Further Docker config for container, e.g., bind mounts:
  - Configuration file created on the fly? Or just command-line args?
  - Trying to change config for existing container is an error, of course.
    Perhaps add an "I don't care if opts can't be used" to avoid this?
- Do we need "no `-it`" support for non-interactive commands?
- Make this work on Windows.
- Named command groups to run in container (e.g., to do dot-home setup).
  From a user config file?
- Work when image shell isn't `/bin/bash`.
- Would be nice to have image build logs stored somewhere rather than just
  spewed to stdtout.
- Consider support for a container naming convention to help prevent
  collisions on multiuser systems. E.g., `dent foo` might first look for
  `cjs-foo`, then `foo`, then fall back to creating `cjs-foo`.

### Setup Script

- Split the setup script into two layers: package updates and
  user-specific stuff so that we can get layer sharing for the
  installed and updated packages for two different users building the
  same distribution.
- Generic "install individual package" function that knows to use apt
  or yum. Or look into using github.com/devexp-db/distgen for this.
- Do `git config --email` etc. before installing etckeeper.
- Consider not updating all packages to latest versions. It takes a
  long time, goes stale anyway, and can easily be done by the user in
  the container itself.

### User Setup and Multiuser

- Build image with all non-system users rather than just current one?
- Split package setup/user setup into separate layers to gain more caching?
- While the image name collision problem between users is fixed, there is
  nothing in place to warn users using the same name for a container as
  another user. Is it worth adding something to automaticaly include the
  user name in the container name?

### Daemonized Processes in Container

- Examples: `ssh-agent`, preview web server.
- User is expected to handle these; we cannot do so.
- Use `ckssh` for shared ssh-agent in container support.
- Provide `-r` switch to restart container, killing all in-container
  processes before running command. (Use command `true` just to kill
  all procs in container.)

### Distro-specific Support

- UTF-8 locale installation doesn't work on Ubuntu 14.04.
- `centos:6` Bash (and `centos:5`, too) throws a segfault for some
  programs (`bash`, `yum`) on a 4.19 kernel (though it works on on
  4.9). Test knows about this, and avoids running the tests. Is there
  something else we can do to help with this? Ideally, dent should be
  able to help with this in as transparent a way possible.

