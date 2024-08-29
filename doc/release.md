How to Release `dent`
=====================

These are the instructions for building a new release of r8format and
uploading it to PyPI. This is of interest only to r8format developers;
users of r8format can safely ignore this.

This is mostly a manual process, but a little bit of it is automated with
the [`build-release`](../build-release) script in this repo.

Release Process
---------------

1. Update the following files:
   - `pyproject.toml`: Remove the `.devN` suffix from the version number.
     (Lack of a `.devN` suffix indicates that a developer didn't add it
     when making a releasable change; in this case just bump the version
     number.)
   - `doc/CHANGELOG.md`: Rename the 'dev' section to the new version number
     and date of release, and add a new (empty) 'dev' section to the top of
     the list of releases.
   - Commit these changes to `main`, but do not push them up to GitHub yet.
     Probably the commit should not include any other changes, and the
     message can be just 'Release 0.x.x'.

2. Build and check the release.
   - Change the current working directory to the project root.
   - Run `./build-release`, which will do a few checks of the configuration
     (these are far from comprehensive), activate the virtualenv, install
     `build` and `twine`, and run `pyproject-build` and `twine check`.
   - Fix anything broken.

3. Do the release
   - `git tag v0.x.x`
   - `git push r main tag v0.x.x`   (replace `r` with your remote name)
   - `./build-release -u`           (ensure you have your API token handy)
