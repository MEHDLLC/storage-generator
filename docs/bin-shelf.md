# The hanging bin rack

## How it carries the bin

Each level is a pair of rails running front to back down either side of the
opening. The bin drops in between them and stops when the flange around its
rim lands on the rail tops.

```
        rail                          rail
   |####|                              |####|
   |####|-- rim rests here     here ---|####|
   |    \____                    ____/      |
   |         \                  /           |     <- bin body, tapering
   |          |    the bin     |            |
```

Consequences worth naming:

- **Nothing sits under the bin.** No shelf to collect crumbs, no drawer runner
  to bind, and the bin lifts straight out.
- **The load path is short.** The rim bears on the rail, the rail is part of
  the side panel, the side panel goes straight down to the bench.
- **It is carried on its two long sides**, along the full 122 mm of the bin,
  rather than at four points.

## Why the fit is forgiving

The rail span is the bin's width just below the rim plus a little clearance:

```
span = bin_width - 2 * lip_overhang + 2 * side_clearance
```

The critical number is `lip_overhang`, and it is not published for any bin I
know of. What rescues the design is that the bin's walls taper toward its base:

- span **slightly too wide** → the bin settles a millimetre lower until the
  taper wedges against the rails, and is carried on the taper
- span **slightly too narrow** → the bin rides a little higher on the rim
  flange, and is carried on the rim

Both hold the bin. What the span cannot be is *so* wide that the rim clears the
rails entirely, which is why the generator refuses a `rail_width` narrower than
the rim overhang and warns when the rim would land on less than 0.8 mm of rail.

Print the `fit-gauge` first if you want the number rather than the estimate.

## Printing without supports

The rack prints standing up, in the orientation it is modelled in. Every
overhang is dealt with in geometry rather than left to the slicer:

| Feature | How it prints |
|---|---|
| Rails cantilevering into the opening | underside cut back at 45 degrees |
| Rail mouths | flared outward at the front, so a bin steers itself in |
| Cut-outs in the back and sides | shaped so no roof is shallower than 45 degrees (see Patterns) |
| Stacking ribs | chamfered on top, and sunk 0.6 mm into the panel so they fuse |
| Side panels and back | plain vertical walls |

The only unsupported spans are the optional continuous front lip and top plate,
which bridge one bay. The generator says so in the print notes when you turn
them on, and `--front-stop tabs` avoids it entirely.

## The options that change the shape

Run `storagegen options bin-shelf` for the full list with defaults. The ones
that change what the thing *is*:

| Option | Choices | Notes |
|---|---|---|
| `columns`, `rows` | 1-6, 1-12 | Bays across and levels up |
| `back` | `cut`, `solid`, `open` | The back is the member that ties the two sides together. `open` is only allowed if `base` and `top` are both there. |
| `sides` | `cut`, `solid` | Cut sides save roughly a quarter of the plastic |
| `base` | `open`, `solid`, `cut` | A floor stiffens the rack and catches spills |
| `top` | `open`, `solid`, `cut` | A top bridges one bay |
| `pattern` | six styles | What gets cut into every surface set to `cut` |
| `front_stop` | `tabs`, `none`, `lip`, `label` | `tabs` is support-free; `lip` and `label` bridge one bay |
| `rail_style` | `full`, `pads` | Pads save plastic on long bays |
| `stackable` | yes/no | Ribs on top, sockets underneath |
| `wall_mount` | yes/no | Adds a keyhole flange above a solid back |

`wall_mount` implies `back = solid`, because the keyholes need something to go
in. The build reports what it actually used in `effective_options`, and the
manifest and listing describe the model rather than the request.

## Patterns

Four surfaces can be cut, and one option decides what they are cut with.

| Pattern | Shape | Default cell / web |
|---|---|---|
| `windows` | Large openings, corners taken off | 28 / 8 mm |
| `grid` | Square holes, top corners taken off | 15 / 5 mm |
| `honeycomb` | Flat-top hexagons | 14 / 5 mm |
| `diamond` | Squares stood on a corner | 16 / 6 mm |
| `round` | Circles | 14 / 5 mm |
| `triangle` | Equilateral triangles, apex up | 20 / 5 mm |

Every one of them keeps a vertical panel printable without support. The rule
is that no edge with material above it may be shallower than 45 degrees:

- hexagons sit **flat-top**. A point-top hexagon's upper edges lie at 30
  degrees from horizontal, which no printer will hold; a flat-top hexagon's
  are at 60 degrees, and its one horizontal span is capped at 12 mm -- the
  hexagon shrinks rather than exceed it.
- diamonds are squares on a corner, so their upper edges sit at exactly 45
  degrees. Triangles point up, never down.
- squares and windows get their top corners taken off at 45 degrees, leaving
  a flat span no longer than 12 mm.
- circles close over gradually, which is why the default cell is modest.

Cut-outs are placed only in the clear band beside each bin: from a margin
above the rail below to a margin below their own rail, so every rail keeps
solid material behind its 45-degree underside. Only whole cells are placed and
the result is centred, so a pattern never trails off into slivers at an edge.
If nothing fits, the surface comes out solid and the run says so rather than
leaving you to notice in the slicer.

Open area runs about 55% for the textured patterns and about 75% for
`windows`, which is why `windows` is both the default and the lightest.

## Things the generator refuses to build

Fast failures with a specific message, rather than a bad print:

- an **open back** with no base or top plate: the rack would come off the bed
  as two loose halves
- a **rail narrower than the rim overhang**: the bin's rim would foul the side
  panels instead of landing on the rails
- a **bin with no rim**: there is nothing for a hanging rack to catch
- anything whose assembled geometry is **not a single connected solid**, which
  is asserted on every build rather than trusted

And warnings that leave the choice to you: too little rim on the rail, a front
stop taller than the headroom above the bin, a rack bigger than the bed you
declared.

## Sizes worth knowing

For the GreenMade Mini Bin, with defaults:

| Configuration | Outside size | Plastic |
|---|---|---|
| 1 x 3 | 100 x 129 x 220 mm | about 150 cm3 |
| 2 x 4 | 197 x 129 x 291 mm | about 330 cm3 |

Level spacing is `bin_height + headroom`, so 71 mm per level by default. A
rack taller than your printer is the case `stackable` exists for: print two
short ones and stack them.
