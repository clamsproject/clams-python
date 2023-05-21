
This directory contains GitHub-related files that help project management and the release process of CLAMS apps. 
To use these workflows, your app must be part of `clamsproject` organization.
To create a new repository under the `clamsproject` organization, here's some naming convention to follow.

* App repositories in the `clamsproject` organization should be prefixed with `app-` (e.g., `app-myapp`).
* An app that wraps an extant tool or application should be suffixed with `-wrapper` (e.g., `app-their-app-wrapper`).
* `LICENSE` file should always contain licensing information of the terminal code. If the app is a wrapper, an additional file containing licensing information of the underlying tool must be placed next to the `LICENSE` file when the original license requires so.

(Your "app name" that you used in `clams develop` to create this scaffolding doesn't have to match the repository name.)

In the `workflows` directory, you'll find;

* `issue-apps-project.yml`: this workflow will add all new issues and PRs to our [`apps` project board](https://github.com/orgs/clamsproject/projects/12).
* `issue-assign.yml`: this workflow will assign an issue to the person who created a branch for the issue. A branch is for an issue when its name starts with the `issueNum-` prefix. (e.g., `3-fix` branch is for issue number 3)
* `issue-close.yml`: this workflow will remove all assignee from closed/merged issues and PRs.
* `publish.yml`: this workflow is the main driver for the app release process. A release process is set to be triggered by **any** tag push. To change the trigger edit `on:` part of the file. To change the trigger edit `on.push.tags` part of the file. ([reference](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#running-your-workflow-only-when-a-push-of-specific-tags-occurs)). 
  * The workflow will
    1. build a container image for the app and push it to [the `clamsproject` ghcr](https://github.com/orgs/clamsproject/packages).
    2. generate app directory entry files and create a PR to [the app directory repository](https://github.com/clamsproject/apps) for registration.
  * **NOTE**: Throughout the entire release process, the git tag that triggered the workflow will be used as the version of the app.
