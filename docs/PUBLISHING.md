# Maintainer publication steps

Suggested repository: `murrayrudd/strategy-financing-feasibility`. Create a new public repository for this paper's replication package. Keep the separate Monster Model technical-review repository private.

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

1. Add its actual URL to `CITATION.cff` (`repository-code`) and the manuscript's data/code availability statement.
2. Check the first GitHub Actions run, which verifies file hashes and runs the replication checks. It has read-only repository permission.
3. Tag the exact manuscript-compatible state as `v1.0.0` and create a release with the tested version number and a concise description of its contents.
4. When SSRN approves the paper and provides its public abstract-page URL, replace `SSRN_URL_PLACEHOLDER` in `README.md` and the paper-link comment in `CITATION.cff`. In the README, make the paper title a Markdown link to that URL, change the status to "Available on SSRN," and append the URL to the provisional paper citation. No paper DOI is required or used.
5. If the author chooses an open-source code license, add it explicitly. Keep third-party data terms separate; a software license cannot replace them.

The SSRN link update is a documentation change; it does not change the frozen model or numerical results. Keep the original release archive available. After uploading the edited README and citation file, refresh `provenance/release_files.json` with the command below so repository verification continues to pass.

After changing tracked files, stage them with `git add -A`, run `python scripts/update_release_manifest.py`, and stage the updated `provenance/release_files.json` before checking or releasing the revised package. The manifest deliberately excludes itself to avoid a circular hash. Keep prior scientific releases unchanged and use a new version for subsequent manuscript results.

GitHub size guidance: <https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github>. The workflow follows GitHub's Python testing pattern: <https://docs.github.com/en/actions/tutorials/build-and-test-code/python>.
