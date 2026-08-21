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
| Windows in the back and sides | corners chamfered at 45 degrees, leaving at most a 12 mm flat top |
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
| `back` | `windowed`, `panel`, `open` | The back is the member that ties the two sides together. `open` is only allowed if `base` and `top` are both plates. |
| `sides` | `windowed`, `solid` | Windowed sides cut roughly a quarter of the plastic |
| `front_stop` | `tabs`, `none`, `lip`, `label` | `tabs` is support-free; `lip` and `label` bridge one bay |
| `base` | `open`, `plate` | A plate stiffens the rack and catches spills |
| `top` | `none`, `plate` | A plate bridges one bay |
| `rail_style` | `full`, `pads` | Pads save plastic on long bays |
| `stackable` | yes/no | Ribs on top, sockets underneath |
| `wall_mount` | yes/no | Adds a keyhole flange above a solid back |

`wall_mount` implies `back = panel`, because the keyholes need something to go
in. The build reports what it actually used in `effective_options`, and the
manifest and listing describe the model rather than the request.

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
