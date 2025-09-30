# ArgoCD CI-Aware Generators Plugin

An ArgoCD ApplicationSet generator plugin that validates CI checks before generating applications. This plugin acts as a gatekeeper, ensuring that only commits that have passed specified CI checks are deployed.

The project addresses a core limitation in the ArgoCD ApplicationSet generators (SCM & PR), which are unaware of CI/CD pipeline statuses. This can lead to the deployment of code from commits with builds that are not ready and pushed to the container registry. This plugin integrates directly into the generator lifecycle to prevent such scenarios.

## Features

- **CI Validation**: Validates GitHub Actions CI checks for a given commit SHA.
- **Stateful Fallback**: If the latest commit fails its checks, the plugin deploys the last known good commit, preventing a broken deployment.
- **Prevents Initial Deployment**: If the first deployment for a branch has failing checks, no application is generated.
- **Flexible Check Matching**: Use regular expressions to specify which CI checks must pass.
- **Broad Generator Support**: Works with both `scmProvider` and `pullRequest` generators.
- **Easy to Install**: Deploys as a standard service within your Kubernetes cluster.

## How It Works

The plugin functions as a custom `getparams` generator, designed to be used within a `matrix` generator in an `ApplicationSet`.

1. **Discovery**: An initial generator (like the SCM or PR provider) discovers candidate repositories, branches, and commit SHAs.
2. **Validation**: The `matrix` generator passes the discovered parameters to this plugin. The plugin receives the commit SHA and a user-defined list of required CI checks (as regular expressions).
3. **CI Check**: It communicates with the SCM provider's API (currently GitHub) to verify that all specified checks for the given commit have completed with a `success` conclusion.
4. **Stateful Decision**:
   - **If checks passed**: The plugin returns the parameters, allowing the `ApplicationSet` to generate the `Application`. It also records the commit SHA as the "last known good state" in a persistent JSON database.
   - **If checks failed**: The plugin checks its database for a previously recorded "last known good state" for that repository and branch. If one exists, it returns the parameters from that older, successful commit. If no prior successful commit is known, it returns an empty list, preventing the `Application` from being generated at all.

This ensures that a failed commit will not be deployed, and the environment will remain on the last stable version.

## Setup and Installation

### 1. Deploy the Plugin

The plugin is a web service that must be deployed where ArgoCD can reach it.

1. **Build and Push the Docker Image**:
   A `Dockerfile` is provided in the `app/` directory. Build and push the image to a container registry of your choice.
   `bash
docker build -t your-registry/argocd-ci-aware-plugin:latest ./app
docker push your-registry/argocd-ci-aware-plugin:latest
`

2. **Deploy to Kubernetes**:
   Deploy the image as a standard Kubernetes Deployment and expose it with a Service. You will need to provide a `GITHUB_TOKEN` as an environment variable to the deployment.

**Environment Variables:**

- `GITHUB_TOKEN`: A GitHub Personal Access Token with `repo` scope (or at least `checks:read`).
- `DB_FILE`: The path to the persistent database file. Defaults to `db.json`. For production, this should be on a persistent volume.

### 2. Configure ArgoCD

1. **Register the Plugin**:
   ArgoCD needs to know about the plugin. Apply a `ConfigMap` to your `argocd` namespace to register it.

```yaml
# argocd-plugin-cm.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-validate-ci-checks-generators-plugin
  namespace: argocd
data: # The address of the service you deployed in the previous step
  baseUrl: "http://<your-plugin-service-name>.<namespace>.svc.cluster.local:8080"
```

Note: The name of this`ConfigMap`will be referenced in the`ApplicationSet`.

2. **Provide GitHub Token for SCM Provider**:
   The `scmProvider` generator also needs a GitHub token to discover repositories. Create a secret in the `argocd` namespace.

```yaml
apiVersion: v1
kind: Secret
metadata:
name: github-token
namespace: argocd
spec:
  stringData:
    token: <YOUR_GITHUB_TOKEN>
```

## Usage Example

To use the plugin, create a `matrix` generator in your `ApplicationSet`. The first generator discovers the commits, and the second is the plugin which validates them.

Here is an example that syncs applications from the `main` branch of a repository, but only if the `build` CI check has passed.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: my-appset
  namespace: argocd
spec:
  generators:
    - matrix:
        generators:
          # 1. Discover commits from the main branch
          - scmProvider:
              github:
                organization: your-org
                allBranches: true
                # Secret created in the setup steps
                tokenRef:
                  secretName: github-token
                  key: token
              filters:
                - repositoryMatch: ^your-repo-name$
                  branchMatch: ^main$

          # 2. Validate the discovered commit
          - plugin:
              # ConfigMap created in the setup steps
              configMapRef:
                name: argocd-validate-ci-checks-generators-plugin
              input:
                parameters:
                  # Tells the plugin this comes from an scmProvider
                  sourceGeneratorType: scm
                  # A list of regex patterns for required CI checks
                  checks_regex:
                    - "build"
                  # Pass the data from the scmProvider to the plugin
                  data:
                    branch: "{{ branch }}"
                    organization: "{{ organization }}"
                    repository: "{{ repository }}"
                    sha: "{{ sha }}"
  template:
    metadata:
      name: "{{repository}}-{{branch}}"
      namespace: argocd
    spec:
      project: default
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
      source:
        repoURL: "https://github.com/{{organization}}/{{repository}}.git"
        targetRevision: "{{sha}}" # The SHA comes from the plugin's output
        path: manifests/
      destination:
        server: "https://kubernetes.default.svc"
        namespace: "{{repository}}"
```

### Plugin Input Parameters

- `sourceGeneratorType` (required): The type of the source generator. Can be `scm` or `pr`.
- `checks_regex` (required): A list of regular expressions to match against the names of GitHub CI checks. All matched checks must be successful.
- `data` (required): The parameters forwarded from the source generator (`scmProvider` or `pullRequest`). The plugin uses this to find the repository and commit to validate.

## Stateful Persistence

The plugin maintains a simple JSON database (`tinydb`) to track the last known good commit SHA for each `(ApplicationSet, repository, branch)` tuple.

For a production setup, it is **critical** to mount a `PersistentVolume` to the path specified by the `DB_FILE` environment variable. This ensures that the state of known good commits is not lost if the plugin pod restarts.

## Development

This project uses `uv` for dependency management.

- **Install dependencies**: `uv sync`
- **Run the server locally**: `uv run serve`
- **Run tests**: `uv run test` (Requires a `GITHUB_TOKEN` environment variable)

## Current Support and Contributions

This plugin is currently implemented for **GitHub Actions** only, as it was developed for a specific use case.

**Contributions are welcome!** We encourage pull requests to add support for other SCM providers such as GitLab, Bitbucket, or others.
