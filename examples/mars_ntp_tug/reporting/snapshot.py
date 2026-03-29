"""ASCII report from :func:`examples.mars_ntp_tug.reporting.extract.extract_mars_ntp_evaluation_report` output."""

from __future__ import annotations

from typing import Any


def _banner(title: str, width: int = 72) -> str:
    line = "=" * width
    return f"{line}\n{title}\n{line}\n"


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return "(no rows)\n"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = " | ".join(f"{{:{w}}}" for w in widths)
    sep = "-+-".join("-" * w for w in widths)
    lines = [fmt.format(*headers), sep]
    for row in rows:
        lines.append(fmt.format(*row))
    return "\n".join(lines) + "\n"


def _wrap_paragraph(text: str, width: int = 72) -> str:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    n = 0
    for w in words:
        add = len(w) if not cur else len(w) + 1
        if n + add > width and cur:
            lines.append(" ".join(cur))
            cur = [w]
            n = len(w)
        else:
            cur.append(w)
            n += add
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines) + "\n"


def format_mars_ntp_report(data: dict[str, Any]) -> str:
    """Render evaluation extract to a readable console report (cargo-jet-style layout)."""
    parts: list[str] = []
    parts.append(_banner("Mars NTP tug (notional) — evaluation snapshot"))

    eval_ok = data.get("evaluation_passed", False)
    reqcheck_ok = data.get("reqcheck_all_passed", False)
    verdict = "PASS" if eval_ok and reqcheck_ok else "FAIL"
    parts.append(
        "Verdict (all constraints + mission reqcheck rows): "
        f"{verdict}\n"
        f"  Evaluator completed without engine failures: {eval_ok}\n"
        f"  Mission reqcheck (requirement_accept_expr) all passed: {reqcheck_ok} "
        f"(count: {data.get('reqcheck_count', 0)})\n"
    )

    thesis = data.get("thesis", {})
    nar = thesis.get("narrative", "")
    if nar:
        parts.append(_banner("Thesis (read this once)"))
        parts.append(_wrap_paragraph(nar))

    failures = data.get("failures") or []
    if failures:
        parts.append("\nFailures:\n")
        for f in failures:
            parts.append(f"  - {f}\n")
    parts.append("\n")

    nk = data.get("napkin_assumptions", {})
    parts.append(_banner("Napkin assumptions (program parameters → desk inputs)"))
    parts.append(
        _table(
            ("quantity", "value", "notes"),
            [
                (k, nk.get(k, ""), "")
                for k in (
                    "napkin_dry_mass_incl_payload_kg",
                    "napkin_transfer_delta_v",
                    "napkin_specific_impulse_vacuum_s",
                    "napkin_reference_gravity",
                    "napkin_thrust_to_weight_start",
                    "napkin_thermal_to_jet_efficiency",
                    "napkin_propellant_loadout_margin",
                    "napkin_jet_kinetic_fraction",
                )
            ],
        ),
    )

    md = data.get("mission_desk_outputs", {})
    parts.append(_banner("Mission desk outputs (ExternalComputeBinding → sim_* attributes)"))
    parts.append(
        _table(
            ("quantity", "value", "notes"),
            [
                (k, md.get(k, ""), "")
                for k in (
                    "sim_propellant_required_kg",
                    "sim_wet_mass_start_kg",
                    "sim_min_vacuum_thrust_kn",
                    "sim_hydrogen_mass_flow_kg_s",
                    "sim_rated_thermal_power_mw",
                )
            ],
        ),
    )

    sm = data.get("scenario_mission", {})
    parts.append(_banner("Scenario aliases (mission closure + reporting)"))
    parts.append(
        _table(
            ("quantity", "value", "notes"),
            [
                ("mission_delta_v_required", sm.get("mission_delta_v_required", ""), "alias of napkin delta-v"),
                ("mission_propellant_required", sm.get("mission_propellant_required", ""), "alias of desk propellant"),
                ("mission_min_vacuum_thrust", sm.get("mission_min_vacuum_thrust", ""), "alias of desk thrust floor"),
            ],
        ),
    )

    ro = data.get("reactor_operating_point", {})
    parts.append(_banner("Reactor core operating point (after run)"))
    parts.append(
        _table(
            ("quantity", "value", "notes"),
            [
                ("rated_thermal_power", ro.get("rated_thermal_power", ""), ""),
                ("hydrogen_mass_flow", ro.get("hydrogen_mass_flow", ""), ""),
                ("u235_mass_fraction", ro.get("u235_mass_fraction", ""), "HEU floor also on req package"),
                ("triso_intact_fraction", ro.get("triso_intact_fraction", ""), ""),
                ("peak_fuel_matrix_temp_ratio", ro.get("peak_fuel_matrix_temp_ratio", ""), ""),
            ],
        ),
    )

    pt = data.get("propulsion_and_tank", {})
    parts.append(_banner("Propellant, nozzle, shield (after run)"))
    parts.append(
        _table(
            ("quantity", "value", "notes"),
            [
                ("tank_propellant_mass", pt.get("tank_propellant_mass", ""), ""),
                ("vacuum_thrust", pt.get("vacuum_thrust", ""), ""),
                ("dose_proxy_at_cargo", pt.get("dose_proxy_at_cargo", ""), "dimensionless proxy"),
                ("dose_limit_proxy", pt.get("dose_limit_proxy", ""), ""),
            ],
        ),
    )

    de = data.get("design_envelope", {})
    parts.append(_banner("Declared design envelope (closure targets)"))
    parts.append(
        _table(
            ("quantity", "value", "notes"),
            [
                ("design_delta_v_capability", de.get("design_delta_v_capability", ""), "vs scenario delta-v"),
                ("design_propellant_capacity", de.get("design_propellant_capacity", ""), "vs scenario propellant"),
            ],
        ),
    )

    parts.append(_banner("Constraints (incl. requirement-linked acceptance)"))
    rows_c: list[tuple[str, ...]] = []
    for c in data.get("constraints", []):
        rows_c.append(
            (
                c.get("name", ""),
                "PASS" if c.get("passed") else "FAIL",
                c.get("requirement_path") or "",
                c.get("allocation_target_path") or "",
            ),
        )
    parts.append(_table(("name", "status", "requirement", "allocatee"), rows_c))

    parts.append(_banner("Formal requirements (authoritative text)"))
    rows_fr: list[tuple[str, ...]] = []
    for r in data.get("formal_requirements", []):
        stmt = r.get("statement", "")
        short = (stmt[:88] + "…") if len(stmt) > 88 else stmt
        rows_fr.append(
            (
                r.get("node_name", ""),
                r.get("verification_kind", ""),
                r.get("package", ""),
                r.get("allocate_to", ""),
                "yes" if r.get("mission_closure_acceptance") else "",
                short.replace("\n", " "),
            ),
        )
    parts.append(
        _table(
            ("id", "verification", "package", "allocate", "closure", "statement (trim)"),
            rows_fr,
        ),
    )

    return "".join(parts)
