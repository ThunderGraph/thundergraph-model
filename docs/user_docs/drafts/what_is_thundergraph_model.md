# What ThunderGraph Model Is

ThunderGraph Model is a Python library for **executable systems modeling**.

Most architecture tools stop at diagrams. This library is for when you want the model to run:

- define structure (`System`, `Part`, ports)
- define value semantics (parameters, attributes, constraints)
- define requirement semantics (`RequirementBlock`, requirement acceptance)
- define behavior (states, events, decisions, sequences, item flow)
- evaluate the whole thing with real quantities and get pass/fail evidence

## What It Is Not

- Not a replacement for all MBSE tools.
- Not a visual modeling suite.
- Not a giant framework that hides execution.

It is intentionally small and explicit: declarations are Python, compile artifacts are inspectable,
and evaluation happens through a clear pipeline.

## Core Promise

A single model can carry:

1. **Architecture** (parts and interfaces)
2. **Physics / math** (unit-aware expressions)
3. **Requirements** (allocation + executable acceptance)
4. **Behavior** (discrete transitions and control flow)
5. **Provenance** (citations and references)

And you can execute all of that against one configured topology.

## Reader Mental Model

There are three layers:

1. **Type time**: class definitions + `define(cls, model)` declarations.
2. **Configuration time**: instantiate one frozen topology (`ConfiguredModel`).
3. **Run time**: evaluate with a fresh `RunContext` per run.

If you keep those three layers separate in your head, the API feels straightforward.

## Primary Entry Points

- Authoring: `tg_model.model` and top-level `tg_model` exports
- Execution: `tg_model.execution`
- External integration: `tg_model.integrations`
- Multi-run studies: `tg_model.analysis`

## Why This Matters

Executable models close the gap between “we wrote requirements” and “we can prove this configuration satisfies them.”

The library is designed so engineers can start small and grow model depth incrementally,
without throwing away earlier work.
