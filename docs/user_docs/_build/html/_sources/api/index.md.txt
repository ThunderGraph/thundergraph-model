# API Reference

**Execution façade:** :class:`~tg_model.execution.configured_model.ConfiguredModel` (``evaluate``), :func:`~tg_model.execution.configured_model.instantiate`, and :meth:`tg_model.model.elements.System.instantiate` are documented under **tg_model.execution** and **tg_model.model** below.

**Composable requirements:** :class:`~tg_model.model.elements.Requirement`, :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement_package`, and dot-navigation :class:`~tg_model.model.refs.RequirementRef`. Declare a leaf requirement with :meth:`~tg_model.model.definition_context.ModelDefinitionContext.requirement` inside :meth:`Requirement.define() <tg_model.model.elements.Element.define>`. After :func:`~tg_model.execution.configured_model.instantiate`, packages appear as :class:`~tg_model.execution.instances.RequirementPackageInstance` under the owning part. Compiled artifacts still label package nodes with internal ``kind`` ``"requirement_block"``. Narrative: {doc}`../user/concepts_requirements` and {doc}`../user/faq`.

```{toctree}
:maxdepth: 2

api_root
api_model
api_execution
api_integrations
api_analysis
```
