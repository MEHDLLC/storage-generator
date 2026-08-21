# Adding a generator

A generator declares its options once and implements `build`. Everything else
— CLI flags, validation, STL and 3MF export, previews, the listing, the
manifest — comes from that one declaration, so the four can never drift apart.

## The shape of one

```python
# src/storagegen/generators/drawer_organiser.py
from .. import geom
from ..generator import BuildResult, Generator, register
from ..mesh_io import PartSet
from ..options import Option, OptionSet, Report


OPTIONS = OptionSet([
    Option("width", 120.0, "Inside width", unit=" mm", minimum=20,
           group="Size"),
    Option("dividers", 2, "Number of dividers", kind="int", minimum=0,
           maximum=12, group="Layout"),
    Option("lid", False, "Include a lid", kind="bool", group="Features"),
])


class DrawerOrganiserGenerator(Generator):
    key = "drawer-organiser"
    title = "Drawer organiser"
    summary = "One sentence a customer would recognise the product from."
    tags = ("storage", "drawer", "organizer", "parametric")
    options = OPTIONS

    def build(self, opt):
        report = Report()
        parts = PartSet()
        parts.add("tray", geom.box([opt["width"], 80.0, 40.0]))
        return BuildResult(
            parts=parts,
            effective_options=opt,
            report=report,
            facts={"outside_mm": [opt["width"], 80.0, 40.0]},
            highlights=["What makes it worth printing"],
            print_notes=["How to print it"],
        )

    def slug(self, opt):
        return f"drawer-organiser_{opt['width']:g}mm_{opt['dividers']}up"


register(DrawerOrganiserGenerator())
```

Then add it to the imports in `src/storagegen/generators/__init__.py` and
`src/storagegen/cli.py`. Importing the module is what registers it.

## What the framework gives you

- **Options.** `kind` is one of `float`, `int`, `bool`, `choice`, `str`.
  `minimum` / `maximum` are enforced with a message naming the limit; a
  `default` of `None` means "fall back to a preset". `group` becomes the CLI
  help section and `listed=False` keeps a knob out of the customer-facing
  options table.
- **Geometry.** `storagegen.geom` wraps manifold3d, so every boolean returns a
  watertight solid. `prism_y`, `prism_x` and `prism_z` extrude a 2-D profile
  along an axis and normalise the winding for you — a clockwise profile used
  to extrude to nothing, silently, which is a bug you only find on the bed.
- **Export.** Anything in the `PartSet` is written as an STL and gathered into
  one 3MF with millimetre units and named objects.
- **Previews.** `context_parts` are rendered alongside the printed parts in a
  cooler colour: the bins a rack holds, the drawer an organiser sits in.
- **Copy.** `listing_title` and `listing_body` are the two hooks worth
  overriding. Everything the description quotes comes from `facts`, so it
  cannot claim a size the model does not have.

## What to hold yourself to

The tests in `tests/` are the standard, not decoration. The ones that earn
their keep are the ones checking things an STL cannot show you:

- **Is it one connected solid?** Assert it inside `build`, not just in a test.
  Removing a cross member is an easy option to add and a silent way to ship a
  model that comes off the bed in pieces.
- **Does the thing it holds actually fit?** Model it (`BinSpec.solid()` is the
  pattern), intersect it against the part, and assert the overlap is zero.
- **Is it actually held?** Zero overlap alone also describes an object floating
  in a hole. Move it a fraction of a millimetre toward the thing that should
  support it and assert it now collides.
- **Do mating features mate?** Translate the part onto a copy of itself and
  assert the stacking features do not foul.
- **Say what you do not know.** If a dimension is an estimate rather than a
  specification, record it as one and let it surface in the listing.
