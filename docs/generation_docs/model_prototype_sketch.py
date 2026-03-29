import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, cast


# --- 1. Tiny semantic model types ------------------------------------------


@dataclass(frozen=True)
class NodeDecl:
    name: str
    kind: str
    target_type: Optional[type] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelDefinitionError(Exception):
    pass


# --- 2. The Reference Objects ----------------------------------------------
# These are NOT runtime instances. They are stable symbolic references used by
# the definition compiler to build a semantic graph.


class Ref:
    def __init__(
        self,
        owner_type: type,
        path: Tuple[str, ...],
        kind: str,
        target_type: Optional[type] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.owner_type = owner_type
        self.path = path
        self.kind = kind
        self.target_type = target_type
        self.metadata = metadata or {}

    @property
    def local_name(self) -> str:
        return ".".join(self.path)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "owner": self.owner_type.__name__,
            "path": list(self.path),
            "kind": self.kind,
        }
        if self.target_type is not None:
            payload["target_type"] = self.target_type.__name__
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.owner_type.__name__}.{self.local_name}>"


class PortRef(Ref):
    pass


class AttributeRef(Ref):
    pass


class PartRef(Ref):
    """
    A reference to a declared part. Accessing attributes on it resolves against
    the compiled definition of the target type.
    """

    def __getattr__(self, name: str) -> Ref:
        if self.target_type is None:
            raise AttributeError(f"{self!r} has no target_type for member lookup")

        compiled = self.target_type._compile_once()
        member = compiled["nodes"].get(name)
        if member is None:
            raise AttributeError(
                f"{self.target_type.__name__} has no declared member named '{name}'"
            )

        chained_path = self.path + (name,)
        kind = member["kind"]
        member_target_type = member["target_type"]
        member_metadata = member["metadata"]

        if kind == "port":
            return PortRef(self.owner_type, chained_path, kind="port", metadata=member_metadata)
        if kind == "attribute":
            return AttributeRef(
                self.owner_type,
                chained_path,
                kind="attribute",
                metadata=member_metadata,
            )
        if kind == "part":
            return PartRef(
                self.owner_type,
                chained_path,
                kind="part",
                target_type=member_target_type,
                metadata=member_metadata,
            )

        raise AttributeError(
            f"Member '{name}' on {self.target_type.__name__} is declared as '{kind}', "
            "which this prototype does not yet project into a typed reference."
        )


# --- 3. The Definition Context (`model`) -----------------------------------


class ModelDefinitionContext:
    """
    The `model` object passed into `define(cls, model)`.

    It is a constrained definition recorder:
    - creates declarations
    - returns typed reference objects
    - validates relationship inputs
    - serializes to a canonical definition structure
    """

    def __init__(self, owner_type: type):
        self.owner_type = owner_type
        self.nodes: Dict[str, NodeDecl] = {}
        self.edges: list[dict[str, Any]] = []
        self._is_frozen = False

    def _check_frozen(self) -> None:
        if self._is_frozen:
            raise RuntimeError("Cannot mutate model after define() phase is complete.")

    def _register_node(
        self,
        *,
        name: str,
        kind: str,
        target_type: Optional[type] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NodeDecl:
        self._check_frozen()
        if name in self.nodes:
            raise ModelDefinitionError(
                f"Duplicate declaration '{name}' in {self.owner_type.__name__}"
            )
        decl = NodeDecl(
            name=name,
            kind=kind,
            target_type=target_type,
            metadata=metadata or {},
        )
        self.nodes[name] = decl
        return decl

    def part(self, name: str, part_type: type) -> PartRef:
        self._register_node(name=name, kind="part", target_type=part_type)
        return PartRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="part",
            target_type=part_type,
        )

    def port(self, name: str, direction: str) -> PortRef:
        self._register_node(name=name, kind="port", metadata={"direction": direction})
        return PortRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="port",
            metadata={"direction": direction},
        )

    def attribute(self, name: str, unit: str) -> AttributeRef:
        self._register_node(name=name, kind="attribute", metadata={"unit": unit})
        return AttributeRef(
            owner_type=self.owner_type,
            path=(name,),
            kind="attribute",
            metadata={"unit": unit},
        )

    def connect(
        self,
        source: PortRef,
        target: PortRef,
        carrying: Optional[str] = None,
    ) -> None:
        self._check_frozen()
        if source.kind != "port" or target.kind != "port":
            raise ModelDefinitionError(
                f"connect() requires PortRef -> PortRef, got {source.kind} -> {target.kind}"
            )
        self.edges.append(
            {
                "kind": "connect",
                "source": source,
                "target": target,
                "carrying": carrying,
            }
        )

    def compile(self) -> Dict[str, Any]:
        """
        Freeze the definition, recursively compile child part types, validate
        edge references, and emit a canonical dictionary structure.
        """
        self._is_frozen = True

        # Recursively ensure child part types are compiled.
        child_types: Dict[str, Dict[str, Any]] = {}
        for decl in self.nodes.values():
            if decl.kind == "part" and decl.target_type is not None:
                child_types[decl.target_type.__name__] = decl.target_type._compile_once()

        # Validate edge references against known declarations.
        for edge in self.edges:
            if edge["kind"] == "connect":
                self._validate_port_ref(edge["source"])
                self._validate_port_ref(edge["target"])

        return {
            "owner": self.owner_type.__name__,
            "nodes": {
                name: {
                    "kind": decl.kind,
                    "target_type": decl.target_type.__name__ if decl.target_type else None,
                    "metadata": dict(decl.metadata),
                }
                for name, decl in self.nodes.items()
            },
            "edges": [
                {
                    "kind": edge["kind"],
                    "source": edge["source"].to_dict(),
                    "target": edge["target"].to_dict(),
                    "carrying": edge["carrying"],
                }
                for edge in self.edges
            ],
            "child_types": child_types,
        }

    def _validate_port_ref(self, ref: Ref) -> None:
        if ref.kind != "port":
            raise ModelDefinitionError(f"Expected a port reference, got {ref.kind}")

        top = ref.path[0]
        owner_decl = self.nodes.get(top)
        if owner_decl is None:
            raise ModelDefinitionError(
                f"Reference '{ref.local_name}' starts with unknown symbol '{top}'"
            )

        # Local port on the owner type.
        if len(ref.path) == 1:
            if owner_decl.kind != "port":
                raise ModelDefinitionError(
                    f"Reference '{ref.local_name}' points to '{top}', which is not a port"
                )
            return

        # Nested port on a child part type.
        if owner_decl.kind != "part" or owner_decl.target_type is None:
            raise ModelDefinitionError(
                f"Reference '{ref.local_name}' expects '{top}' to be a part"
            )

        child_def = owner_decl.target_type._compile_once()
        member_name = ref.path[1]
        member = child_def["nodes"].get(member_name)
        if member is None:
            raise ModelDefinitionError(
                f"Reference '{ref.local_name}' points to missing member '{member_name}' "
                f"on {owner_decl.target_type.__name__}"
            )
        if member["kind"] != "port":
            raise ModelDefinitionError(
                f"Reference '{ref.local_name}' points to '{member_name}', which is not a port"
            )


# --- 4. Base model classes --------------------------------------------------


class Element:
    _compiled_definition: Optional[Dict[str, Any]] = None

    @classmethod
    def define(cls, model: ModelDefinitionContext) -> None:
        pass

    @classmethod
    def _compile_once(cls) -> Dict[str, Any]:
        if cls._compiled_definition is None:
            ctx = ModelDefinitionContext(cls)
            cls.define(ctx)
            cls._compiled_definition = ctx.compile()
        return cls._compiled_definition


class Part(Element):
    pass


class System(Element):
    pass


# --- 5. User-authored model definitions ------------------------------------


class Battery(Part):
    @classmethod
    def define(cls, model: ModelDefinitionContext) -> None:
        model.attribute("charge", unit="%")
        model.port("power_out", direction="out")


class Motor(Part):
    @classmethod
    def define(cls, model: ModelDefinitionContext) -> None:
        model.port("power_in", direction="in")
        model.attribute("torque", unit="N*m")


class DriveSystem(System):
    @classmethod
    def define(cls, model: ModelDefinitionContext) -> None:
        battery = model.part("battery", Battery)
        motor = model.part("motor", Motor)

        model.connect(
            source=cast(PortRef, battery.power_out),
            target=cast(PortRef, motor.power_in),
            carrying="electrical_power",
        )


# --- 6. Small framework demo ------------------------------------------------


def _demo_pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2)


def _demo_summarize_compiled(compiled: Dict[str, Any]) -> None:
    """Walk the compiled dict in plain language (prototype introspection)."""
    owner = compiled["owner"]
    print(f"\n  Owner: {owner}")
    print("  Local nodes:")
    for name, info in compiled["nodes"].items():
        tgt = info.get("target_type")
        extra = f" -> {tgt}" if tgt else ""
        meta = info.get("metadata") or {}
        meta_s = f", metadata={meta}" if meta else ""
        print(f"    - {name!r}: kind={info['kind']}{extra}{meta_s}")

    edges = compiled.get("edges") or []
    print(f"  Edges ({len(edges)}):")
    for e in edges:
        src = ".".join(e["source"]["path"])
        dst = ".".join(e["target"]["path"])
        carry = e.get("carrying")
        carry_s = f" carrying={carry!r}" if carry else ""
        print(f"    - {e['kind']}: {src} -> {dst}{carry_s}")

    children = compiled.get("child_types") or {}
    print(f"  Embedded child type definitions ({len(children)}):")
    for type_name, child in children.items():
        n_nodes = len(child.get("nodes") or {})
        n_edges = len(child.get("edges") or [])
        print(f"    - {type_name}: {n_nodes} nodes, {n_edges} edges (nested)")


if __name__ == "__main__":
    print("=== Per-type compile (Motor/Battery also pulled in by DriveSystem) ===")
    bat = Battery._compile_once()
    mot = Motor._compile_once()
    drv = DriveSystem._compile_once()

    print("\n--- Battery._compiled_definition (full JSON) ---")
    print(_demo_pretty(bat))
    _demo_summarize_compiled(bat)

    print("\n--- DriveSystem._compiled_definition (full JSON) ---")
    print(_demo_pretty(drv))
    _demo_summarize_compiled(drv)

    print("\n--- What lives on each class after compile ---")
    for cls in (Battery, Motor, DriveSystem):
        c = cls._compiled_definition
        assert c is not None
        child_keys = list((c.get("child_types") or {}).keys())
        print(
            f"  {cls.__name__}._compiled_definition: "
            f"id={id(c):#x}, "
            f"{len(c['nodes'])} local nodes, "
            f"{len(c.get('edges') or [])} edges, "
            f"child_types={child_keys or '[]'}"
        )

    same_battery = drv["child_types"]["Battery"] is Battery._compiled_definition
    same_motor = drv["child_types"]["Motor"] is Motor._compiled_definition
    print(
        "\n--- child_types reuse ---\n"
        f"  DriveSystem's embedded Battery/Motor defs are the same dict objects as\n"
        f"  Battery._compiled_definition / Motor._compiled_definition: "
        f"{same_battery and same_motor}"
    )

    print(
        "\nNote: these dicts are the type-level semantic snapshot. "
        "They are not runtime 'DriveSystem instances' with live battery/motor objects."
    )
