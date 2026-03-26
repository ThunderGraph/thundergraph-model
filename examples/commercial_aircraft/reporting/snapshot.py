"""ASCII report from :func:`commercial_aircraft.reporting.extract.extract_cargo_jet_evaluation_report` output."""

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


def format_cargo_jet_report(data: dict[str, Any]) -> str:
    """Render evaluation extract to a readable console report."""
    parts: list[str] = []
    parts.append(_banner("Atlas-400F (notional) — evaluation snapshot"))

    thesis = data.get("thesis", {})
    eval_ok = data.get("evaluation_passed", False)
    margin_ok = thesis.get("margin_non_negative", False)
    envelope_ok = thesis.get("declared_envelope_constraints_passed", False)
    verdict = "PASS" if eval_ok and margin_ok and envelope_ok else "FAIL"
    parts.append(f"Verdict (desk margin + declared-envelope constraints + other checks): {verdict}\n")
    nar = thesis.get("narrative", "")
    if nar:
        parts.append(_banner("Thesis (read this once)"))
        parts.append(_wrap_paragraph(nar))
    margin_km = thesis.get("mission_range_margin_km", "")
    parts.append("Mission desk track:\n")
    parts.append(f"  Margin (raw): {thesis.get('mission_range_margin_m', '')}\n")
    if margin_km:
        parts.append(f"  Margin (rounded): ~{margin_km}\n")
    parts.append(f"  Margin ≥ 0: {margin_ok}\n")
    parts.append(
        "Declared envelope track (maximum takeoff weight / payload / range vs parameters):\n"
    )
    parts.append(f"  Envelope constraints all passed: {envelope_ok}\n")
    parts.append(f"  Evaluator completed without engine failures: {eval_ok}\n")
    failures = data.get("failures") or []
    if failures:
        parts.append("\nFailures:\n")
        for f in failures:
            parts.append(f"  - {f}\n")
    parts.append("\n")

    sc = data.get("scenario", {})
    parts.append(_banner("Scenario inputs"))
    parts.append(
        _table(
            ("quantity", "value", "human (length)"),
            [
                ("scenario_payload_mass_kg", sc.get("scenario_payload_mass_kg", ""), ""),
                ("scenario_design_range_m", sc.get("scenario_design_range_m", ""), sc.get("scenario_design_range_human", "")),
                (
                    "mission_desk_baseline_max_range_m",
                    sc.get("mission_desk_baseline_max_range_m", ""),
                    sc.get("mission_desk_baseline_human", ""),
                ),
            ],
        ),
    )

    ac = data.get("aircraft", {})
    parts.append(_banner("Aircraft roll-up / envelope"))
    parts.append(
        _table(
            ("quantity", "value", "human (length)"),
            [
                ("operating_empty_mass_kg", ac.get("operating_empty_mass_kg", ""), ""),
                ("modeled_max_payload_kg", ac.get("modeled_max_payload_kg", ""), ""),
                (
                    "modeled_max_design_range_m",
                    ac.get("modeled_max_design_range_m", ""),
                    ac.get("modeled_max_design_range_human", ""),
                ),
                ("notional_mzfw_kg", ac.get("notional_mzfw_kg", ""), ""),
                ("notional_mtow_kg", ac.get("notional_mtow_kg", ""), ""),
                ("notional_trip_fuel_kg", ac.get("notional_trip_fuel_kg", ""), ""),
            ],
        ),
    )

    wing = data.get("wing", {})
    parts.append(_banner("Wing external compute"))
    parts.append(
        _table(
            ("quantity", "value", "human (length)"),
            [("wing_structural_intensity_kg_per_m", wing.get("wing_structural_intensity_kg_per_m", ""), "")],
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

    parts.append(_banner("Level-1 requirements (authoritative text)"))
    rows_l1: list[tuple[str, ...]] = []
    for r in data.get("l1_requirements", []):
        stmt = r.get("statement", "")
        short = (stmt[:88] + "…") if len(stmt) > 88 else stmt
        vk = r.get("verification_kind", "")
        rows_l1.append(
            (
                r.get("node_name", ""),
                vk,
                r.get("block", ""),
                r.get("allocate_to", ""),
                "yes" if r.get("mission_closure_acceptance") else "",
                short.replace("\n", " "),
            ),
        )
    parts.append(
        _table(
            ("id", "verification", "block", "allocate", "closure", "statement (trim)"),
            rows_l1,
        ),
    )

    prov = data.get("external_provenance") or {}
    if prov:
        parts.append(_banner("External tool provenance (by slot id)"))
        for sid, p in prov.items():
            parts.append(f"  {sid}\n    {p!r}\n")

    return "".join(parts)
