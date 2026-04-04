# HPC datacenter example (colocation facility)

Small **ThunderGraph Model** program: a structural :class:`~tg_model.model.elements.System` root with scenario parameters, a facility :class:`~tg_model.model.elements.Part`, and **Level-1** obligations authored as composable :class:`~tg_model.model.elements.Requirement` types registered with **`model.requirement_package`** (see [`program.py`](./program.py)).

- **`L1HpcRequirements`** — two atomic requirements using the **advanced leaf reqcheck** helpers **`requirement_input`**, **`requirement_attribute`**, and **`requirement_accept_expr`** for grid import and auxiliary cooling envelope checks.
- **`L1HpcRoot`** — nests **`L1HpcRequirements`** under **`hpc`**; the program root registers **`model.requirement_package("l1", L1HpcRoot)`** and **`allocate`**s each requirement to the facility part with **`inputs=...`**.

## How to run (import path)

The wheel ships **`tg_model`** only. Put **`thundergraph-model/examples`** on **`PYTHONPATH`** so **`import hpc_datacenter`** resolves:

```bash
cd thundergraph-model
export PYTHONPATH="examples${PYTHONPATH:+:$PYTHONPATH}"
uv run python -c "from hpc_datacenter import HpcDatacenterProgram; print(HpcDatacenterProgram.compile()['owner'])"
```

## Evaluate (recommended)

Use **`ConfiguredModel.evaluate`** with **`ValueSlot`** keys (same pattern as the [user quickstart](../../docs/user_docs/user/quickstart.md)):

```python
from unitflow import Quantity
from unitflow.catalogs.si import kW

from hpc_datacenter import HpcDatacenterProgram

cm = HpcDatacenterProgram.instantiate()
fac = cm.facility
result = cm.evaluate(
    inputs={
        cm.equipment_electrical_load_kw: Quantity(30.0, kW),
        cm.auxiliary_cooling_load_kw: Quantity(8.0, kW),
        fac.grid_import_capacity_kw: Quantity(50.0, kW),
        fac.max_cooling_kw: Quantity(12.0, kW),
    },
)
assert result.passed
```

Parameter sweeps are demonstrated in [`notebooks/hpc_datacenter_parameter_sweep.ipynb`](../../notebooks/hpc_datacenter_parameter_sweep.ipynb).

## Tests

From **`thundergraph-model/`**:

```bash
uv run pytest tests/integration/test_hpc_datacenter_smoke.py -v --no-cov
```
