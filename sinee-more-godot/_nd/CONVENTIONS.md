# Development Conventions

- GDScript is the default implementation language.
- Keep main.tscn stable until a real architectural reason requires changing it.
- Prefer small composable scenes over one giant scene.
- Campaign-specific code stays under campaign/<world>/ until proven reusable.
- Promote abstractions to core/ only when real reuse justifies them.
- Keep presentation logic separable from narrative data where practical.
- Master generated media belongs in durable media storage; project assets are runtime-ready derivatives.
- Follow consequential mutations with the strongest cheap Godot validation available.
- Add smoke/regression coverage as behavior appears.
- Preserve already-working D2 mechanics by default.
- Never commit .godot/, ci-out/, builds/, exports/, or transient probes.
