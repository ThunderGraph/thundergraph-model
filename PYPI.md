# thundergraph-model

**Executable systems modeling in Python.**

Model systems as `System`, `Part`, and `Requirement` types, compile dependency graphs, evaluate unit-aware expressions, bind external compute, and keep traceability in one strict library.

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Installation

```bash
pip install thundergraph-model
```

## Quick Start

```python
from unitflow import kg
from tg_model import Part, System
from tg_model.execution import instantiate


class PayloadAnalysis(Part):
    @classmethod
    def define(cls, model):
        payload = model.parameter_ref(PayloadSystem, "payload_kg")
        model.attribute("payload_with_margin_kg", unit=kg, expr=payload * 1.1)
        model.constraint("payload_limit", expr=payload <= 1000 * kg)


class PayloadSystem(System):
    @classmethod
    def define(cls, model):
        model.parameter("payload_kg", unit=kg, required=True)
        model.part("analysis", PayloadAnalysis)


cm = instantiate(PayloadSystem)
result = cm.evaluate(inputs={cm.root.payload_kg: 800 * kg})

print(result.passed)
print(result.outputs[cm.root.analysis.payload_with_margin_kg.stable_id])
```

## What It Covers

- Unit-aware parameters, attributes, and executable constraints
- Structural modeling with `System`, `Part`, and composable `Requirement` packages
- Requirement allocation and traceability
- Graph compilation and evaluation from Python-authored models
- External compute integration through `ExternalComputeBinding`
- Discrete behavior and scenario modeling

## Documentation

Documentation and project information are available at [thundergraph.ai/open-source/thundergraph-model](http://localhost:3002/open-source/thundergraph-model).

## Links

- [ThunderGraph](https://www.thundergraph.ai)
- [GitHub Repository](https://github.com/ThunderGraph/thundergraph-model)

## License

Apache 2.0
