# Overview

ThunderGraph Model lets you model systems as executable code:

- structure (`System`, `Part`, ports)
- values (parameters, attributes, constraints)
- requirements (`Requirement` subclasses, `model.composed_of`, `model.allocate`, constraints, citations)
- behavior (events, transitions, decisions, sequences, item flow)

## Start here

1. {doc}`install`
2. {doc}`quickstart` — recommended path: **`instantiate`** → **`ConfiguredModel.evaluate`** (slot handles + quantities); explicit `compile_graph` + `Evaluator` is the advanced path.
3. {doc}`mental_model`

## Concrete concept examples

- {doc}`concepts_requirements`
- {doc}`concepts_external_compute`

## API reference

- {doc}`../api/index`
