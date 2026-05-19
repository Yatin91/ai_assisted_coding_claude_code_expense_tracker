---
description: Ships the current feature by committing, pushing, creating PR, merging, and cleaning up the branch automatically using GitHub MCP.
tools:
  - bash
  - mcp__github
---

# Ship Feature Command

## Step 1 - Commit
Run git add . and commit all changes with an appropriate conventional commit message based on what was changed.

## Step 2 - Push
Push the current feature branch to origin.

## Step 3 - Create Pull Request
Using the GitHub MCP, create a pull request into main with:
- A proper title based on the feature
- A detailed description of what was changed
- Definition of done checklist

## Step 4 - Merge
Using the GitHub MCP, merge the pull request using squash merge.

## Step 5 - Cleanup
- Delete the remote feature branch
- Switch to main locally
- Pull latest changes from origin main
- Delete the local feature branch

## Final Output
Confirm all steps completed successfully and show current branch.