Changelog
=========

This file follows most, but not all, of the conventions described at
[keepachangelog.com]. Especially we always use [ISO dates]. Subsections or
notations for changes may include Added, Changed, Deprecated, Fixed,
Removed, and Security.

Release version numbers follow the [Python packaging
specifications][pyver], which are generally consistent with [semantic
versioning][semver]: are _major.minor.patch_ Development versions use the
version number of the _next_ release with _.devN_ appended; `1.2.3.dev4` is
considered to be earlier than `1.2.3`.

On any change to the programs or libraries (not, generally, the tests), the
previous release version number is bumped and `.devN` is appended to it, if
this hasn't already been done. A `.devN` suffix will stay until the next
release, though its _N_ need not be bumped unless the developer feels the
need.

Releases are usually tagged with `vN.N.N`. Potentially not all releases
will be tagged, but specific releases can also be fetched via the Git
commit ID.

### dev
- Significant internal re-organisation; should not be visible to users.
- Test: Now use -B NAME to specify images; all args after -- passed to pytest
- Test: Now use mypy.
- Fixed: User with UID 1000 is now removed before trying to add the dent user.
  (Many users of dent had the same UID, and collided with images such as
  Ubuntu that already include a user with UID 1000.)

### 1.0.0 (2024-08-29)
- Initial release as Python distribution package.
- Test: Add -c "small clean" option that clears/reinstalls virtualenv
- Note: This was also released as 1.0.0.dev3 and 1.0.0.beta1.



<!-------------------------------------------------------------------->
[ISO dates]: https://xkcd.com/1179/
[keepachangelog.com]: https://keepachangelog.com/
[pyver]: https://packaging.python.org/en/latest/specifications/version-specifiers/#version-specifiers
[semver]: https://en.wikipedia.org/wiki/Software_versioning#Semantic_versioning
