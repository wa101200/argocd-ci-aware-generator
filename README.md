# ArgoCD CI-Aware Generators Plugin

An ArgoCD ApplicationSet generator plugin that validates CI checks before generating applications. This plugin acts as a gatekeeper, ensuring that only commits that have passed specified CI checks are deployed.

The project addresses a core limitation in the ArgoCD ApplicationSet generators (SCM & PR), which are unaware of CI/CD pipeline statuses. This can lead to the deployment of code from commits with builds that are not ready and pushed to the container registry. This plugin integrates directly into the generator lifecycle to prevent such scenarios.

## How It Works

The plugin functions as a custom `getparams` generator, designed to be used within a `matrix` generator in an `ApplicationSet`.

1. **Discovery**: An initial generator (like the SCM or PR provider) discovers candidate repositories, branches, and commit SHAs.
2. **Validation**: The `matrix` generator passes the discovered parameters to this plugin. The plugin receives the commit SHA and a user-defined list of required CI checks (as regular expressions).
3. **CI Check**: It communicates with the SCM provider's API to verify that all specified checks for the given commit have completed with a `success` conclusion.
4. **Stateful Decision**:
   - **If checks passed**: The plugin returns the parameters, allowing the `ApplicationSet` to generate the `Application`. It also records the commit SHA as the "last known good state" in a persistent JSON database.
   - **If checks failed**: The plugin checks its database for a previously recorded "last known good state" for that repository and branch. If one exists, it returns the parameters from that older, successful commit. If no prior successful commit is known, it returns an empty list, preventing the `Application` from being generated at all.

This ensures that a failed commit will not be deployed, and the environment will remain on the last stable version.

## Current Support and Contributions

This plugin is currently implemented for **GitHub Actions** only, as it was developed for a specific use case.

**Contributions are welcome\!** We encourage pull requests to add support for other SCM providers such as GitLab, Bitbucket, or others.
