# Coding Agent Handoff

## Original Goal

Restate the parent task and the delegated child task.

## Delegation Result

State whether the delegated task is completed, partially completed, or blocked.

## Work Completed

Summarize concrete changes, findings, and verification performed by the child
agent.

## Parent Review Notes

List facts, assumptions, unresolved risks, and any patch details the parent
agent should review before accepting the result.

## Parent Next Step

Give the parent agent one concrete next action.

## Current Status

Describe the current state after the child-agent work.

## User Constraints

List user constraints and preferences that still apply.

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

Give the next agent a concrete first action.

## Risks / Unknowns

List unresolved risks, missing context, or things that need verification.

## Instructions For Next Agent

Before continuing, inspect the current repository state and compare it with this
handoff. Do not blindly trust this document. Do not apply patches or run
dangerous commands unless the user explicitly asks.
