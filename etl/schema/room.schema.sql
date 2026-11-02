-- room.schema.sql — the room: its size, surfaces (the floor and the walls) and the items on them, the
-- column, door and lintel, the tiles, the norms the design checks use, and what labour is priced from.

CREATE TABLE room_room (
  id INTEGER PRIMARY KEY CONSTRAINT "the room is one row" CHECK (id = 1),
  length REAL NOT NULL CONSTRAINT "the room's length is more than 0" CHECK (length > 0 AND length < 1e308),
  width  REAL NOT NULL CONSTRAINT "the room's width is more than 0"  CHECK (width > 0 AND width < 1e308),
  ceiling REAL NOT NULL CONSTRAINT "the ceiling is more than 0" CHECK (ceiling > 0 AND ceiling < 1e308),
  -- every hole at least this far from a tile joint (or exactly on one); length is along the first wall, width the second
  joint_clearance REAL NOT NULL CONSTRAINT "the joint clearance is more than 0" CHECK (joint_clearance > 0 AND joint_clearance < 1e308)
) STRICT;
CREATE TABLE room_label  (code TEXT NOT NULL, lang TEXT NOT NULL REFERENCES language(code), text TEXT NOT NULL,
                          PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE room_symbol (code TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;

-- what room.py works out for labour to be priced by (a code each), and what it measures
CREATE TABLE room_take_off (
  code TEXT PRIMARY KEY,
  pos INTEGER NOT NULL UNIQUE,
  measure TEXT NOT NULL CONSTRAINT "a take-off is an area or a length" CHECK (measure IN ('area', 'length'))
) STRICT;

CREATE TABLE room_tile (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE,
  product TEXT NOT NULL UNIQUE REFERENCES materials_product(id),
  tiling_height REAL NOT NULL CONSTRAINT "a tiling height is more than 0" CHECK (tiling_height > 0 AND tiling_height < 1e308),  -- tiled up to this on a wall
  fill TEXT NOT NULL                         -- its colour on the drawings
) STRICT;
CREATE TABLE room_tile_text (tile TEXT NOT NULL REFERENCES room_tile(id), lang TEXT NOT NULL REFERENCES language(code),
                             name TEXT NOT NULL, PRIMARY KEY (tile, lang)) STRICT;

-- the room's surfaces: the floor, and the walls in order round the plan
CREATE TABLE room_surface (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE,
  kind TEXT NOT NULL CONSTRAINT "a surface is a wall or the floor" CHECK (kind IN ('wall', 'floor')),
  ref TEXT NOT NULL UNIQUE,                  -- its letter on the drawings (M, N, W, F)
  tile TEXT NOT NULL REFERENCES room_tile(id),
  UNIQUE (id, kind)
) STRICT;
CREATE TABLE room_wall (
  surface TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'wall' CONSTRAINT "a wall's surface is a wall" CHECK (kind = 'wall'),
  -- waterproofed up to this height (higher within the shower zone, by the zone's own); elevation: it gets an
  -- elevation drawing (a wall with items must have one)
  waterproofing REAL NOT NULL CONSTRAINT "a waterproofing height is more than 0" CHECK (waterproofing > 0 AND waterproofing < 1e308),
  elevation INTEGER NOT NULL CONSTRAINT "elevation is 0 or 1" CHECK (elevation IN (0, 1)),
  FOREIGN KEY (surface, kind) REFERENCES room_surface(id, kind)
) STRICT;
CREATE TABLE room_wall_text (wall TEXT NOT NULL REFERENCES room_wall(surface), lang TEXT NOT NULL REFERENCES language(code),
                             name TEXT NOT NULL, PRIMARY KEY (wall, lang)) STRICT;
CREATE TABLE room_wall_assumed (wall TEXT NOT NULL REFERENCES room_wall(surface),
  key TEXT NOT NULL CONSTRAINT "a wall's assumed key is one of its values" CHECK (key IN ('waterproofing')),
  how TEXT NOT NULL, PRIMARY KEY (wall, key)) STRICT;
CREATE TABLE room_floor (
  surface TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'floor' CONSTRAINT "the floor's surface is the floor" CHECK (kind = 'floor'),
  drain TEXT NOT NULL REFERENCES room_item(id),        -- the floor item the floor falls to
  -- the wet (low) side of the step falls 1 in fall_wet to the drain; the dry (high) side 1 in fall_dry towards the step
  fall_wet REAL NOT NULL CONSTRAINT "the wet side's fall is more than 0" CHECK (fall_wet > 0 AND fall_wet < 1e308),
  fall_dry REAL NOT NULL CONSTRAINT "the dry side's fall is more than 0" CHECK (fall_dry > 0 AND fall_dry < 1e308),
  FOREIGN KEY (surface, kind) REFERENCES room_surface(id, kind)
) STRICT;
CREATE TABLE room_floor_assumed (floor TEXT NOT NULL REFERENCES room_floor(surface),
  key TEXT NOT NULL CONSTRAINT "the floor's assumed key is one of its values" CHECK (key IN ('fall_wet', 'fall_dry')),
  how TEXT NOT NULL, PRIMARY KEY (floor, key)) STRICT;

-- The existing column, at the x = 0 end of its wall; the rest of its wall is new. width: along its wall; depth:
-- through the wall; into_room: how far its bathroom face stands proud of the wall's. room.py sets out the door
-- opening beside it and the lintel over it (README rule 1).
CREATE TABLE room_column (
  id INTEGER PRIMARY KEY CONSTRAINT "the column is one row" CHECK (id = 1),
  width REAL NOT NULL CONSTRAINT "the column's width is more than 0" CHECK (width > 0 AND width < 1e308),
  depth REAL NOT NULL CONSTRAINT "the column's depth is more than 0" CHECK (depth > 0 AND depth < 1e308),
  into_room REAL NOT NULL CONSTRAINT "into_room is 0 or more" CHECK (into_room >= 0 AND into_room < 1e308),
  wall TEXT NOT NULL REFERENCES room_wall(surface),
  remark TEXT                                -- for editors (English, not printed): where its figures came from
) STRICT;
CREATE TABLE room_column_text (lang TEXT PRIMARY KEY REFERENCES language(code), name TEXT NOT NULL) STRICT;
CREATE TABLE room_column_note (lang TEXT PRIMARY KEY REFERENCES language(code), note TEXT NOT NULL) STRICT;
CREATE TABLE room_door (
  id INTEGER PRIMARY KEY CONSTRAINT "the door is one row" CHECK (id = 1),
  product TEXT NOT NULL REFERENCES materials_product(id),
  -- hinge: the end of the opening the leaf is hinged at (start: the column side); swing: in, into the room, or out
  hinge TEXT NOT NULL CONSTRAINT "the door is hinged at the start or the end" CHECK (hinge IN ('start', 'end')),
  swing TEXT NOT NULL CONSTRAINT "the door opens in or out" CHECK (swing IN ('in', 'out'))
) STRICT;
CREATE TABLE room_door_note (lang TEXT PRIMARY KEY REFERENCES language(code), note TEXT NOT NULL) STRICT;
CREATE TABLE room_lintel (
  id INTEGER PRIMARY KEY CONSTRAINT "the lintel is one row" CHECK (id = 1),
  product TEXT NOT NULL REFERENCES materials_product(id),
  -- bearing: onto the wall; the column end sits in a shallow pocket
  bearing REAL NOT NULL CONSTRAINT "the lintel's bearing is more than 0" CHECK (bearing > 0 AND bearing < 1e308)
) STRICT;
CREATE TABLE room_lintel_note (lang TEXT PRIMARY KEY REFERENCES language(code), note TEXT NOT NULL) STRICT;

-- An item on a surface. It names a product (taking its name and size from it) or has its own name. Its shape is
-- the one shape table it has a row in (below), which holds its position and size: x, y its centre — on a wall, x
-- from the corner on your right facing the wall from inside, y above the lower finished floor; on the floor, x from
-- the second wall, y from the first — w, h, d width, height, depth out from the wall. A wall's shapes: rect, circle
-- (a fitting), point (a services point or fixing), zone (the wet zone), opening; the floor's: rect, step (a level
-- change, high: which end is higher). fitting: for a services point or fixing, the fitting it serves (it must sit
-- within it). A note says why or how — never where: it doesn't repeat what the drawing shows.
CREATE TABLE room_item (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL,
  surface TEXT NOT NULL REFERENCES room_surface(id),
  product TEXT REFERENCES materials_product(id),
  fitting TEXT,                              -- the fitting this item serves, on the same wall
  UNIQUE (surface, id),
  UNIQUE (surface, pos),
  FOREIGN KEY (surface, fitting) REFERENCES room_item(surface, id)
) STRICT;
-- w, h and d may be left out when the item's product has them (code: what a shape needs, once sizes are filled in)
CREATE TABLE room_item_rect (item TEXT PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  h REAL CONSTRAINT "h is more than 0" CHECK (h IS NULL OR (h > 0 AND h < 1e308)),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308))) STRICT;
CREATE TABLE room_item_circle (item TEXT PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308))) STRICT;
CREATE TABLE room_item_point (item TEXT PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308)) STRICT;
CREATE TABLE room_item_zone (item TEXT PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308)),
  waterproofing REAL CONSTRAINT "a zone's waterproofing height is more than 0"
                     CHECK (waterproofing IS NULL OR (waterproofing > 0 AND waterproofing < 1e308))) STRICT;
CREATE TABLE room_item_opening (item TEXT PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  h REAL CONSTRAINT "h is more than 0" CHECK (h IS NULL OR (h > 0 AND h < 1e308))) STRICT;
CREATE TABLE room_item_step (item TEXT PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  h REAL NOT NULL CONSTRAINT "a step's h is more than 0" CHECK (h > 0 AND h < 1e308),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308)),
  high TEXT NOT NULL CONSTRAINT "a step's high side is the start or the end" CHECK (high IN ('start', 'end'))) STRICT;
CREATE TABLE room_item_name (item TEXT NOT NULL REFERENCES room_item(id), lang TEXT NOT NULL REFERENCES language(code),
                             name TEXT NOT NULL, PRIMARY KEY (item, lang)) STRICT;      -- its own name (no product)
CREATE TABLE room_item_note (item TEXT NOT NULL REFERENCES room_item(id), lang TEXT NOT NULL REFERENCES language(code),
                             note TEXT NOT NULL, PRIMARY KEY (item, lang)) STRICT;
CREATE TABLE room_item_assumed (item TEXT NOT NULL REFERENCES room_item(id),
  key TEXT NOT NULL CONSTRAINT "an item's assumed key is one of its values" CHECK (key IN ('x', 'y', 'w', 'h', 'd', 'waterproofing')),
  how TEXT NOT NULL, PRIMARY KEY (item, key)) STRICT;

-- a norm (a code each) a design check holds the room to, with its source (README rule 10)
CREATE TABLE room_norm (
  code TEXT PRIMARY KEY,
  pos INTEGER NOT NULL UNIQUE,
  item TEXT REFERENCES room_item(id),
  value REAL NOT NULL CONSTRAINT "a norm's value is more than 0" CHECK (value > 0 AND value < 1e308),
  standard TEXT NOT NULL, url TEXT NOT NULL,
  checked TEXT NOT NULL CONSTRAINT "a norm's checked is a date, YYYY-MM-DD" CHECK (date(checked) IS checked)
) STRICT;
CREATE TABLE room_norm_text (norm TEXT NOT NULL REFERENCES room_norm(code), lang TEXT NOT NULL REFERENCES language(code),
                             name TEXT NOT NULL, PRIMARY KEY (norm, lang)) STRICT;

CREATE VIEW room_item_shape AS      -- each item's shape, from the table it is in
  SELECT item, 'rect' AS shape FROM room_item_rect UNION ALL SELECT item, 'circle' FROM room_item_circle UNION ALL
  SELECT item, 'point' FROM room_item_point UNION ALL SELECT item, 'zone' FROM room_item_zone UNION ALL
  SELECT item, 'opening' FROM room_item_opening UNION ALL SELECT item, 'step' FROM room_item_step;

CREATE VIEW check_room_rows AS
  SELECT t || ' has ' || n || ' rows, not 1' FROM (
    SELECT 'room_room' t, (SELECT count(*) FROM room_room) n UNION ALL
    SELECT 'room_floor', (SELECT count(*) FROM room_floor) UNION ALL
    SELECT 'room_column', (SELECT count(*) FROM room_column) UNION ALL
    SELECT 'room_door', (SELECT count(*) FROM room_door) UNION ALL
    SELECT 'room_lintel', (SELECT count(*) FROM room_lintel)) WHERE n <> 1;
CREATE VIEW check_room_surfaces AS
  SELECT 'there are ' || n || ' ' || kind || ' surfaces, not ' || want FROM (
    SELECT 'wall' AS kind, 4 AS want, (SELECT count(*) FROM room_surface WHERE kind = 'wall') AS n UNION ALL
    SELECT 'floor', 1, (SELECT count(*) FROM room_surface WHERE kind = 'floor')) WHERE n <> want
  UNION ALL SELECT 'a wall surface has no wall row, or the floor no floor row' FROM room_surface s
  WHERE (s.kind = 'wall' AND s.id NOT IN (SELECT surface FROM room_wall)) OR (s.kind = 'floor' AND s.id NOT IN (SELECT surface FROM room_floor));
CREATE VIEW check_room_tiles AS SELECT 'there is no tile' FROM (SELECT count(*) n FROM room_tile) WHERE n = 0;
CREATE VIEW check_room_item_one_shape AS
  SELECT 'item ' || i.id || ' has ' || count(s.item) || ' shapes, not 1' FROM room_item i LEFT JOIN room_item_shape s ON s.item = i.id
  GROUP BY i.id HAVING count(s.item) <> 1;
CREATE VIEW check_room_item_product_or_name AS
  SELECT 'item ' || id || CASE WHEN product IS NULL THEN ' has neither a product nor a name' ELSE ' has a product and its own name' END
  FROM room_item WHERE (product IS NULL) IS NOT (id IN (SELECT item FROM room_item_name));
CREATE VIEW check_room_item_own_size AS        -- an item with a product takes its size from it
  SELECT 'item ' || i.id || ' has a product, so it takes its size from it' FROM room_item i
  WHERE i.product IS NOT NULL AND (
    EXISTS (SELECT 1 FROM room_item_rect r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.h IS NOT NULL OR r.d IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_circle r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.d IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_zone r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.d IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_opening r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.h IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_step r WHERE r.item = i.id AND r.d IS NOT NULL));
CREATE VIEW check_room_item_shape_on_surface AS
  SELECT 'item ' || i.id || ' is a ' || s.shape || ', which can''t be on the ' || f.kind
  FROM room_item i JOIN room_item_shape s ON s.item = i.id JOIN room_surface f ON f.id = i.surface
  WHERE (f.kind = 'floor' AND s.shape NOT IN ('rect', 'step')) OR (f.kind = 'wall' AND s.shape = 'step');
CREATE VIEW check_room_floor_rect_no_h AS
  SELECT 'item ' || i.id || ' is a rect on the floor, which is seen from above, so it has no h'
  FROM room_item i JOIN room_item_rect r ON r.item = i.id JOIN room_surface f ON f.id = i.surface WHERE f.kind = 'floor' AND r.h IS NOT NULL;
CREATE VIEW check_room_item_fitting_on_wall AS
  SELECT 'item ' || i.id || ' serves a fitting, which only a wall item does'
  FROM room_item i JOIN room_surface s ON s.id = i.surface WHERE i.fitting IS NOT NULL AND s.kind <> 'wall';
CREATE VIEW check_room_drain_on_floor AS
  SELECT 'the drain ' || f.drain || ' is not on the floor' FROM room_floor f JOIN room_item i ON i.id = f.drain WHERE i.surface IS NOT f.surface;
-- the room needs a particular kind of product in each slot (a link to the materials list, README rule 6)
CREATE VIEW check_room_product_kinds AS
  SELECT 'the door names a product that isn''t a door frame' FROM room_door d JOIN materials_product p ON p.id = d.product
  WHERE p.kind IS NOT 'door_frame'
  UNION ALL SELECT 'the lintel names a product that isn''t a lintel' FROM room_lintel l JOIN materials_product p ON p.id = l.product
  WHERE p.kind IS NOT 'lintel'
  UNION ALL SELECT 'tile ' || t.id || ' names a product that isn''t a tile' FROM room_tile t JOIN materials_product p ON p.id = t.product
  WHERE p.kind IS NOT 'tile';
CREATE VIEW check_room_items_drawn AS
  SELECT 'wall ' || w.surface || ' has items but no elevation' FROM room_wall w
  WHERE NOT w.elevation AND w.surface IN (SELECT surface FROM room_item);

-- ---------- for reading: every item as people say it
CREATE VIEW show_room_item AS
  SELECT i.pos, s.ref, coalesce(wt.name, 'floor') AS surface, coalesce(n.name, p.name) AS item, sh.shape,
         coalesce(r.x, c.x, pt.x, z.x, o.x, st.x) AS x, coalesce(r.y, c.y, pt.y, o.y) AS y,
         coalesce(r.w, c.w, z.w, o.w) AS w, coalesce(r.h, o.h, st.h) AS h, coalesce(r.d, c.d, z.d, st.d) AS d,
         st.high, z.waterproofing, coalesce(fn.name, fp.name) AS serves,
         (SELECT group_concat(key, ', ') FROM room_item_assumed a WHERE a.item = i.id) AS assumed
  FROM room_item i JOIN room_surface s ON s.id = i.surface
  LEFT JOIN room_wall_text wt ON wt.wall = s.id AND wt.lang = 'en'
  LEFT JOIN room_item_name n ON n.item = i.id AND n.lang = 'en'
  LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en'
  LEFT JOIN room_item_shape sh ON sh.item = i.id
  LEFT JOIN room_item_rect r ON r.item = i.id LEFT JOIN room_item_circle c ON c.item = i.id
  LEFT JOIN room_item_point pt ON pt.item = i.id LEFT JOIN room_item_zone z ON z.item = i.id
  LEFT JOIN room_item_opening o ON o.item = i.id LEFT JOIN room_item_step st ON st.item = i.id
  LEFT JOIN room_item f ON f.id = i.fitting
  LEFT JOIN room_item_name fn ON fn.item = f.id AND fn.lang = 'en'
  LEFT JOIN materials_product_text fp ON fp.product = f.product AND fp.lang = 'en';
