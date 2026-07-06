# Coding Agent Handoff

## Original Goal

State the parent task and why a bounded subtask is being delegated.

## Delegation Request

Explain the reason for delegation and the expected child-agent role.

## Child Agent Task

Describe exactly what the child agent should inspect, change, or verify.

## Acceptance Criteria

List the conditions that mean the delegated task is complete.

## Return Instructions

Tell the child agent what to include in the result bundle or summary.

## Current Status

Describe the parent task state before delegation.

## User Constraints

List user constraints and preferences that still apply to the delegated task.

## Repo State

Record the repository branch, dirty state, and relevant git status. Mark
unknown values as `unknown`.

## Changed Files

List changed files and summarize the reason for each change.

## Commands Run

List important commands and their outcomes. Separate read-only inspection
commands from bundle-writing actions. Do not invent command results.

## Test State

Separate passing, failing, and not-run checks.

## Failed Attempts

List attempted approaches that did not work and why.

## Current Hypothesis

State the best current explanation for the remaining issue. Mark it as an
assumption if it has not been verified.

## Next Recommended Step

Give the child agent a concrete first action.

## Risks / Unknowns

List unresolved risks, missing context, or things that need verification.

## Instructions For Next Agent

Before continuing, inspect the current repository state and compare it with this
handoff. Do not blindly trust this document. Do not apply patches or run
dangerous commands unless the user explicitly asks.
