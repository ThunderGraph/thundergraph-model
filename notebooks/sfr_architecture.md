# SFR plant demo — architecture + requirement allocations

Illustrative **sodium-cooled fast reactor** plant slice. Requirements live on **`SodiumCooledReactorPlant`**; **`allocate`** edges show which subsystem owns evidence for each requirement. **`CoreInstrumentationPart`** has no requirement allocation (telemetry path only). See `sodium_fast_reactor_demo.ipynb`.

```mermaid
flowchart TB
  subgraph req["Requirements on SodiumCooledReactorPlant"]
    direction LR
    RH[(req_hot_leg)]
    RD[(req_decay_heat)]
    RE[(req_export_floor)]
    RS[(req_shutdown_margin)]
    RP[(req_protection_ready)]
  end
  subgraph plant["Subsystem parts"]
    direction LR
    P["PrimarySodiumLoopPart<br/>hot-leg envelope"]
    D["DecayHeatRemovalPart<br/>DHR vs decay load"]
    C["PowerConversionPart<br/>net export band"]
    R["ReactivityControlPart<br/>shutdown margin"]
    I["CoreInstrumentationPart<br/>excore telemetry"]
    K["ReactorProtectionPart<br/>rack + sequence"]
  end
  RH -->|allocate| P
  RD -->|allocate| D
  RE -->|allocate| C
  RS -->|allocate| R
  RP -->|allocate| K
  I -->|"structural connect<br/>ReactorSignal (item)"| K
```
