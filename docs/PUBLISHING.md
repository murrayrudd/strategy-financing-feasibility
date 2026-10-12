# Maintainer publication steps

Repository: <https://github.com/murrayrudd/strategy-financing-feasibility>. This public repository contains the paper's replication package. Keep the separate Monster Model technical-review repository private.

The package is ready to initialize from an extracted ZIP:

```bash
python scripts/verify_release.py
python reproduce.py verify
# Only when starting from an extracted archive, rather than an existing clone:
git init -b main
git add .
git commit -m "Prepare Strategy financing feasibility replication release 1.0.0"
git remote add origin https://github.com/murrayrudd/strategy-financing-feasibility.git
git push -u origin main
```

Create the repository before pushing. Configure Git with the maintainer's own identity if required. The `.gitignore` excludes expanded data, regenerated transaction ledgers, and local build logs. Every retained file is below 20 MiB; the bundled data can be uploaded through GitHub's file interface as well as Git.

After the repository exists:

1. Keep the actual repository URL in `CITATION.cff` (`repository-code`) and the manuscript's data/code availability statement. The current citation file already records the repository URL.
2. Check the first GitHub Actions run, which verifies file hashes and runs the replication checks. It has read-only repository permission.
3. Tag the exact manuscript-compatible state as `v1.0.0` and create a release with the tested version number and a concise description of its contents.
4. The paper DOI is `10.2139/ssrn.7593458`, with canonical link <https://doi.org/10.2139/ssrn.7593458> and SSRN page <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7593458>. Keep these links consistent between `README.md` and `CITATION.cff`. The DOI belongs under `preferred-citation` in the citation file; do not assign the paper DOI to the software package itself.
5. If the author chooses an open-source code license, add it explicitly. Keep third-party data terms separate; a software license cannot replace them.

Paper-link and citation updates are documentation changes; they do not change the frozen model or numerical results. Keep the original release archive available. The release manifest also checks documentation files. Changing the README or citation metadata without refreshing `provenance/release_files.json` therefore causes the automated integrity check to fail, even when the model is unchanged.

After changing tracked files, stage them with `git add -A`, run `python scripts/update_release_manifest.py`, and stage the updated `provenance/release_files.json` before checking or releasing the revised package. The manifest deliberately excludes itself to avoid a circular hash. Keep prior scientific releases unchanged and use a new version for subsequent manuscript results.

GitHub size guidance: <https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github>. The workflow follows GitHub's Python testing pattern: <https://docs.github.com/en/actions/tutorials/build-and-test-code/python>.

## Updating documentation without breaking verification

For future citation or README edits, use a local clone and commit the edited files and refreshed manifest together:

```bash
git add -A
python scripts/update_release_manifest.py
git add provenance/release_files.json
python scripts/verify_release.py
git commit -m "Update paper metadata and release checksums"
git push
```

If you edit a file directly on GitHub, refresh and commit the manifest afterward from a clone of that updated branch. Do not disable the integrity check to clear a failure. The workflow runs the model verification only after the release-file hashes pass.
