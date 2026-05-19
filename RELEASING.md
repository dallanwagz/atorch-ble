# Releasing atorch-ble

Releases are published to PyPI via [GitHub Actions trusted publishing](https://docs.pypi.org/trusted-publishers/) — no long-lived API tokens live in repo secrets.

## One-time setup (PyPI trusted publisher)

This must be done once before the first release can be published.

1. Sign in to https://pypi.org/manage/account/publishing/
2. Add a new **pending publisher** with these values:
   - **PyPI Project Name**: `atorch-ble`
   - **Owner**: `dallanwagz`
   - **Repository name**: `atorch-ble`
   - **Workflow filename**: `release.yml`
   - **Environment name**: `pypi`
3. Save. PyPI will associate this GitHub Actions identity with the project name. The first run of `release.yml` will claim the name.

After the first publish lands, the publisher entry becomes a regular publisher (no longer "pending").

## Cutting a release

1. Ensure `main` is at the commit you want to release.
2. Confirm `pyproject.toml`'s `[project].version` matches the intended tag (e.g. `0.1.0` for `v0.1.0`).
3. Confirm `CHANGELOG.md` has an entry for the new version with a real date.
4. Create and push the tag:
   ```bash
   git tag -a v0.1.0 -m "atorch-ble v0.1.0"
   git push origin v0.1.0
   ```
5. The `Release` workflow fires on the tag push, builds the sdist + wheel, and uploads to PyPI via OIDC.
6. Verify on https://pypi.org/project/atorch-ble/

## Post-publish smoke test

In a clean virtualenv:

```bash
python -m venv /tmp/atorch-smoke
/tmp/atorch-smoke/bin/pip install atorch-ble==0.1.0
/tmp/atorch-smoke/bin/python -c "from atorch_ble import AtorchBleParser, UsbMeterReading; print(AtorchBleParser, UsbMeterReading)"
```

The import must succeed and print the class objects.
