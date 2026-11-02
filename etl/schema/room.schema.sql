CREATE TABLE room_room (
  -- the room part — the room: its size, surfaces (the floor and the walls) and the items on them, the
  -- column, door and lintel, the tiles, the norms the design checks use, and what labour is priced from.
  id INTEGER PRIMARY KEY CONSTRAINT "the room is one row" CHECK (id = 1),
  length REAL NOT NULL CONSTRAINT "the room's length is more than 0" CHECK (length > 0 AND length < 1e308),
  width  REAL NOT NULL CONSTRAINT "the room's width is more than 0"  CHECK (width > 0 AND width < 1e308),
  ceiling REAL NOT NULL CONSTRAINT "the ceiling is more than 0" CHECK (ceiling > 0 AND ceiling < 1e308),
  -- every hole at least this far from a tile joint (or exactly on one); length is along the first wall, width the second
  joint_clearance REAL NOT NULL CONSTRAINT "the joint clearance is more than 0" CHECK (joint_clearance > 0 AND joint_clearance < 1e308)
) STRICT;
CREATE TABLE room_label  (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') NOT NULL, lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), text TEXT CONSTRAINT "text isn't empty" CHECK (text <> '') NOT NULL,
                          PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE room_symbol (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY, value TEXT CONSTRAINT "value isn't empty" CHECK (value <> '') NOT NULL) STRICT;

CREATE TABLE room_take_off (
  -- what room.py works out for labour to be priced by (a code each), and what it measures
  code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY,
  pos INTEGER NOT NULL UNIQUE,
  measure TEXT CONSTRAINT "measure isn't empty" CHECK (measure <> '') NOT NULL CONSTRAINT "a take-off is an area or a length" CHECK (measure IN ('area', 'length'))
) STRICT;

CREATE TABLE room_tile (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL UNIQUE REFERENCES materials_product(id),
  tiling_height REAL NOT NULL CONSTRAINT "a tiling height is more than 0" CHECK (tiling_height > 0 AND tiling_height < 1e308),  -- tiled up to this on a wall
  fill TEXT CONSTRAINT "fill isn't empty" CHECK (fill <> '') NOT NULL                         -- its colour on the drawings
) STRICT;
CREATE TABLE room_tile_text (tile TEXT CONSTRAINT "tile isn't empty" CHECK (tile <> '') NOT NULL REFERENCES room_tile(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                             name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (tile, lang)) STRICT;

CREATE TABLE room_surface (
  -- the room's surfaces: the floor, and the walls in order round the plan
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  kind TEXT CONSTRAINT "kind isn't empty" CHECK (kind <> '') NOT NULL CONSTRAINT "a surface is a wall or the floor" CHECK (kind IN ('wall', 'floor')),
  ref TEXT CONSTRAINT "ref isn't empty" CHECK (ref <> '') NOT NULL UNIQUE,                  -- its letter on the drawings (M, N, W, F)
  tile TEXT CONSTRAINT "tile isn't empty" CHECK (tile <> '') NOT NULL REFERENCES room_tile(id)
) STRICT;
CREATE TABLE room_wall (
  surface TEXT CONSTRAINT "surface isn't empty" CHECK (surface <> '') PRIMARY KEY REFERENCES room_surface(id),
  -- waterproofed up to this height (higher within the shower zone, by the zone's own); elevation: it gets an
  -- elevation drawing (a wall with items must have one)
  waterproofing REAL NOT NULL CONSTRAINT "a waterproofing height is more than 0" CHECK (waterproofing > 0 AND waterproofing < 1e308),
  elevation INTEGER NOT NULL CONSTRAINT "elevation is 0 or 1" CHECK (elevation IN (0, 1))
) STRICT;
CREATE TABLE room_wall_text (wall TEXT CONSTRAINT "wall isn't empty" CHECK (wall <> '') NOT NULL REFERENCES room_wall(surface), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                             name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (wall, lang)) STRICT;
CREATE TABLE room_wall_assumed (wall TEXT CONSTRAINT "wall isn't empty" CHECK (wall <> '') NOT NULL REFERENCES room_wall(surface),
  key TEXT CONSTRAINT "key isn't empty" CHECK (key <> '') NOT NULL CONSTRAINT "a wall's assumed key is one of its values" CHECK (key IN ('waterproofing')),
  how TEXT CONSTRAINT "how isn't empty" CHECK (how <> '') NOT NULL, PRIMARY KEY (wall, key)) STRICT;
CREATE TABLE room_floor (
  surface TEXT CONSTRAINT "surface isn't empty" CHECK (surface <> '') PRIMARY KEY REFERENCES room_surface(id),
  drain TEXT CONSTRAINT "drain isn't empty" CHECK (drain <> '') NOT NULL REFERENCES room_item(id),        -- the floor item the floor falls to
  -- the wet (low) side of the step falls 1 in fall_wet to the drain; the dry (high) side 1 in fall_dry towards the step
  fall_wet REAL NOT NULL CONSTRAINT "the wet side's fall is more than 0" CHECK (fall_wet > 0 AND fall_wet < 1e308),
  fall_dry REAL NOT NULL CONSTRAINT "the dry side's fall is more than 0" CHECK (fall_dry > 0 AND fall_dry < 1e308)
) STRICT;
CREATE TABLE room_floor_assumed (floor TEXT CONSTRAINT "floor isn't empty" CHECK (floor <> '') NOT NULL REFERENCES room_floor(surface),
  key TEXT CONSTRAINT "key isn't empty" CHECK (key <> '') NOT NULL CONSTRAINT "the floor's assumed key is one of its values" CHECK (key IN ('fall_wet', 'fall_dry')),
  how TEXT CONSTRAINT "how isn't empty" CHECK (how <> '') NOT NULL, PRIMARY KEY (floor, key)) STRICT;

CREATE TABLE room_column (
  -- The existing column, at the x = 0 end of its wall; the rest of its wall is new. width: along its wall; depth:
  -- through the wall; into_room: how far its bathroom face stands proud of the wall's. room.py sets out the door
  -- opening beside it and the lintel over it (README rule 1).
  id INTEGER PRIMARY KEY CONSTRAINT "the column is one row" CHECK (id = 1),
  width REAL NOT NULL CONSTRAINT "the column's width is more than 0" CHECK (width > 0 AND width < 1e308),
  depth REAL NOT NULL CONSTRAINT "the column's depth is more than 0" CHECK (depth > 0 AND depth < 1e308),
  into_room REAL NOT NULL CONSTRAINT "into_room is 0 or more" CHECK (into_room >= 0 AND into_room < 1e308),
  wall TEXT CONSTRAINT "wall isn't empty" CHECK (wall <> '') NOT NULL REFERENCES room_wall(surface),
  remark TEXT CONSTRAINT "remark isn't empty" CHECK (remark <> '')                                -- for editors (English, not printed): where its figures came from
) STRICT;
CREATE TABLE room_column_text (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL) STRICT;
CREATE TABLE room_column_note (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL) STRICT;
CREATE TABLE room_door (
  id INTEGER PRIMARY KEY CONSTRAINT "the door is one row" CHECK (id = 1),
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL REFERENCES materials_product(id),
  -- hinge: the end of the opening the leaf is hinged at (start: the column side); swing: in, into the room, or out
  hinge TEXT CONSTRAINT "hinge isn't empty" CHECK (hinge <> '') NOT NULL CONSTRAINT "the door is hinged at the start or the end" CHECK (hinge IN ('start', 'end')),
  swing TEXT CONSTRAINT "swing isn't empty" CHECK (swing <> '') NOT NULL CONSTRAINT "the door opens in or out" CHECK (swing IN ('in', 'out'))
) STRICT;
CREATE TABLE room_door_note (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL) STRICT;
CREATE TABLE room_lintel (
  id INTEGER PRIMARY KEY CONSTRAINT "the lintel is one row" CHECK (id = 1),
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL REFERENCES materials_product(id),
  -- bearing: onto the wall; the column end sits in a shallow pocket
  bearing REAL NOT NULL CONSTRAINT "the lintel's bearing is more than 0" CHECK (bearing > 0 AND bearing < 1e308)
) STRICT;
CREATE TABLE room_lintel_note (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL) STRICT;

CREATE TABLE room_item (
  -- An item on a surface. It names a product (taking its name and size from it) or has its own name. Its shape is
  -- the one shape table it has a row in (below), which holds its position and size: x, y its centre — on a wall, x
  -- from the corner on your right facing the wall from inside, y above the lower finished floor; on the floor, x from
  -- the second wall, y from the first — w, h, d width, height, depth out from the wall. A wall's shapes: rect, circle
  -- (a fitting), point (a services point or fixing), zone (the wet zone), opening; the floor's: rect, step (a level
  -- change, high: which end is higher). fitting: for a services point or fixing, the fitting it serves (it must sit
  -- within it). A note says why or how — never where: it doesn't repeat what the drawing shows.
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL,
  surface TEXT CONSTRAINT "surface isn't empty" CHECK (surface <> '') NOT NULL REFERENCES room_surface(id),
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') REFERENCES materials_product(id),
  fitting TEXT CONSTRAINT "fitting isn't empty" CHECK (fitting <> '')
    CONSTRAINT "an item doesn't serve itself" CHECK (fitting IS NULL OR fitting <> id),                              -- the fitting this item serves, on the same wall
  UNIQUE (surface, id),
  UNIQUE (surface, pos),
  FOREIGN KEY (surface, fitting) REFERENCES room_item(surface, id)
) STRICT;
CREATE TABLE room_item_rect (
  -- w, h and d may be left out when the item's product has them (code: what a shape needs, once sizes are filled in)
  item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  h REAL CONSTRAINT "h is more than 0" CHECK (h IS NULL OR (h > 0 AND h < 1e308)),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308))) STRICT;
CREATE TABLE room_item_circle (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308))) STRICT;
CREATE TABLE room_item_point (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308)) STRICT;
CREATE TABLE room_item_zone (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308)),
  waterproofing REAL CONSTRAINT "a zone's waterproofing height is more than 0"
                     CHECK (waterproofing IS NULL OR (waterproofing > 0 AND waterproofing < 1e308))) STRICT;
CREATE TABLE room_item_opening (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  y REAL NOT NULL CONSTRAINT "y is 0 or more" CHECK (y >= 0 AND y < 1e308),
  w REAL CONSTRAINT "w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  h REAL CONSTRAINT "h is more than 0" CHECK (h IS NULL OR (h > 0 AND h < 1e308))) STRICT;
CREATE TABLE room_item_step (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') PRIMARY KEY REFERENCES room_item(id),
  x REAL NOT NULL CONSTRAINT "x is 0 or more" CHECK (x >= 0 AND x < 1e308),
  h REAL NOT NULL CONSTRAINT "a step's h is more than 0" CHECK (h > 0 AND h < 1e308),
  d REAL CONSTRAINT "d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308)),
  high TEXT CONSTRAINT "high isn't empty" CHECK (high <> '') NOT NULL CONSTRAINT "a step's high side is the start or the end" CHECK (high IN ('start', 'end'))) STRICT;
CREATE TABLE room_item_name (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') NOT NULL REFERENCES room_item(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                             name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL,                  -- its own name (an item with no product)
                             PRIMARY KEY (item, lang)) STRICT;
CREATE TABLE room_item_note (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') NOT NULL REFERENCES room_item(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                             note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL, PRIMARY KEY (item, lang)) STRICT;
CREATE TABLE room_item_assumed (item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') NOT NULL REFERENCES room_item(id),
  key TEXT CONSTRAINT "key isn't empty" CHECK (key <> '') NOT NULL CONSTRAINT "an item's assumed key is one of its values" CHECK (key IN ('x', 'y', 'w', 'h', 'd', 'waterproofing')),
  how TEXT CONSTRAINT "how isn't empty" CHECK (how <> '') NOT NULL, PRIMARY KEY (item, key)) STRICT;

CREATE TABLE room_norm (
  -- a norm (a code each) a design check holds the room to, with its source (README rule 10)
  code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY,
  pos INTEGER NOT NULL UNIQUE,
  item TEXT CONSTRAINT "item isn't empty" CHECK (item <> '') REFERENCES room_item(id),
  value REAL NOT NULL CONSTRAINT "a norm's value is more than 0" CHECK (value > 0 AND value < 1e308),
  standard TEXT CONSTRAINT "standard isn't empty" CHECK (standard <> '') NOT NULL, url TEXT CONSTRAINT "url isn't empty" CHECK (url <> '') NOT NULL,
  checked TEXT CONSTRAINT "checked isn't empty" CHECK (checked <> '') NOT NULL CONSTRAINT "a norm's checked is a date, YYYY-MM-DD" CHECK (date(checked) IS checked)
) STRICT;
CREATE TABLE room_norm_text (norm TEXT CONSTRAINT "norm isn't empty" CHECK (norm <> '') NOT NULL REFERENCES room_norm(code), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                             name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (norm, lang)) STRICT;

CREATE VIEW room_item_shape AS      -- each item's shape, from the table it is in
  -- two groups of 3: D1 allows at most 5 terms in a compound SELECT
  SELECT * FROM (SELECT item, 'rect' AS shape FROM room_item_rect UNION ALL SELECT item, 'circle' FROM room_item_circle
                 UNION ALL SELECT item, 'point' FROM room_item_point)
  UNION ALL
  SELECT * FROM (SELECT item, 'zone' AS shape FROM room_item_zone UNION ALL SELECT item, 'opening' FROM room_item_opening
                 UNION ALL SELECT item, 'step' FROM room_item_step);

CREATE VIEW room_check_rows AS
  SELECT column1 || ' has ' || column2 || ' rows, not 1' FROM (VALUES
    ('room_room', (SELECT count(*) FROM room_room)),
    ('room_floor', (SELECT count(*) FROM room_floor)),
    ('room_column', (SELECT count(*) FROM room_column)),
    ('room_door', (SELECT count(*) FROM room_door)),
    ('room_lintel', (SELECT count(*) FROM room_lintel))) WHERE column2 <> 1;
CREATE VIEW room_check_surfaces AS
  SELECT 'there are ' || n || ' ' || kind || ' surfaces, not ' || want FROM (
    SELECT 'wall' AS kind, 4 AS want, (SELECT count(*) FROM room_surface WHERE kind = 'wall') AS n UNION ALL
    SELECT 'floor', 1, (SELECT count(*) FROM room_surface WHERE kind = 'floor')) WHERE n <> want
  UNION ALL SELECT 'a wall surface has no wall row, or the floor no floor row' FROM room_surface s
  WHERE (s.kind = 'wall' AND s.id NOT IN (SELECT surface FROM room_wall)) OR (s.kind = 'floor' AND s.id NOT IN (SELECT surface FROM room_floor));
CREATE VIEW room_check_surface_kinds AS
  -- a wall's row is on a wall surface, the floor's on the floor surface
  SELECT 'a wall row is on a surface that is the ' || s.kind FROM room_wall w JOIN room_surface s ON s.id = w.surface WHERE s.kind <> 'wall'
  UNION ALL SELECT 'the floor row is on a surface that is a ' || s.kind FROM room_floor f JOIN room_surface s ON s.id = f.surface WHERE s.kind <> 'floor';
CREATE VIEW room_check_tiles AS SELECT 'there is no tile' FROM (SELECT count(*) n FROM room_tile) WHERE n = 0;
CREATE VIEW room_check_item_one_shape AS
  SELECT 'item ' || i.id || ' has ' || count(s.item) || ' shapes, not 1' FROM room_item i LEFT JOIN room_item_shape s ON s.item = i.id
  GROUP BY i.id HAVING count(s.item) <> 1;
CREATE VIEW room_check_item_product_or_name AS
  SELECT 'item ' || id || CASE WHEN product IS NULL THEN ' has neither a product nor a name' ELSE ' has a product and its own name' END
  FROM room_item WHERE (product IS NULL) IS NOT (id IN (SELECT item FROM room_item_name));
CREATE VIEW room_check_item_own_size AS        -- an item with a product takes its size from it
  SELECT 'item ' || i.id || ' has a product, so it takes its size from it' FROM room_item i
  WHERE i.product IS NOT NULL AND (
    EXISTS (SELECT 1 FROM room_item_rect r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.h IS NOT NULL OR r.d IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_circle r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.d IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_zone r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.d IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_opening r WHERE r.item = i.id AND (r.w IS NOT NULL OR r.h IS NOT NULL)) OR
    EXISTS (SELECT 1 FROM room_item_step r WHERE r.item = i.id AND r.d IS NOT NULL));
CREATE VIEW room_check_item_shape_on_surface AS
  SELECT 'item ' || i.id || ' is a ' || s.shape || ', which can''t be on the ' || f.kind
  FROM room_item i JOIN room_item_shape s ON s.item = i.id JOIN room_surface f ON f.id = i.surface
  WHERE (f.kind = 'floor' AND s.shape NOT IN ('rect', 'step')) OR (f.kind = 'wall' AND s.shape = 'step');
CREATE VIEW room_check_floor_rect_no_h AS
  SELECT 'item ' || i.id || ' is a rect on the floor, which is seen from above, so it has no h'
  FROM room_item i JOIN room_item_rect r ON r.item = i.id JOIN room_surface f ON f.id = i.surface WHERE f.kind = 'floor' AND r.h IS NOT NULL;
CREATE VIEW room_check_item_fitting_on_wall AS
  SELECT 'item ' || i.id || ' serves a fitting, which only a wall item does'
  FROM room_item i JOIN room_surface s ON s.id = i.surface WHERE i.fitting IS NOT NULL AND s.kind <> 'wall';
CREATE VIEW room_check_drain_on_floor AS
  SELECT 'the drain ' || f.drain || ' is not on the floor' FROM room_floor f JOIN room_item i ON i.id = f.drain WHERE i.surface IS NOT f.surface;
CREATE VIEW room_check_product_kinds AS
  -- the room needs a particular kind of product in each slot (a link to the materials list, README rule 6)
  SELECT 'the door names a product that isn''t a door frame' FROM room_door d JOIN materials_product p ON p.id = d.product
  WHERE p.kind IS NOT 'door_frame'
  UNION ALL SELECT 'the lintel names a product that isn''t a lintel' FROM room_lintel l JOIN materials_product p ON p.id = l.product
  WHERE p.kind IS NOT 'lintel'
  UNION ALL SELECT 'tile ' || t.id || ' names a product that isn''t a tile' FROM room_tile t JOIN materials_product p ON p.id = t.product
  WHERE p.kind IS NOT 'tile';
CREATE VIEW room_check_items_drawn AS
  SELECT 'wall ' || w.surface || ' has items but no elevation' FROM room_wall w
  WHERE NOT w.elevation AND w.surface IN (SELECT surface FROM room_item);

CREATE VIEW room_show_item AS
  -- ---------- for reading: every item as people say it
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

CREATE VIEW room_check_fitting_loop AS
  -- a chain of fittings ends: following what each item serves never comes back to it (A serves B, B serves A). A recursive
  -- query walks each chain; it stops at the start, or at an item it has passed already, so it ends even on a loop
  WITH RECURSIVE up(start, at, path) AS (
    SELECT id, fitting, id FROM room_item WHERE fitting IS NOT NULL
    UNION ALL
    SELECT u.start, i.fitting, u.path || ' ' || u.at FROM up u JOIN room_item i ON i.id = u.at
    WHERE i.fitting IS NOT NULL AND u.at <> u.start AND instr(u.path, u.at) = 0)
  SELECT 'item ' || start || ' serves a chain of fittings that comes back to it' FROM up WHERE at = start;

CREATE VIEW room_show_fitting AS
  -- ---------- for reading: each chain of fittings as a tree, flat, in order — the fitting first, then what serves it, each
  -- with its depth (0 for the fitting) and the chain from the fitting down. A recursive query, read like a thread
  WITH RECURSIVE tree(item, root, depth, chain, sort) AS (
    SELECT i.id, i.id, 0, coalesce(n.name, p.name), printf('%08d', s.pos) || printf('%08d', i.pos)
    FROM room_item i JOIN room_surface s ON s.id = i.surface
    LEFT JOIN room_item_name n ON n.item = i.id AND n.lang = 'en'
    LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en'
    WHERE i.fitting IS NULL AND i.id IN (SELECT fitting FROM room_item)
    UNION ALL
    SELECT i.id, t.root, t.depth + 1, t.chain || ' › ' || coalesce(n.name, p.name), t.sort || '.' || printf('%08d', i.pos)
    FROM tree t JOIN room_item i ON i.fitting = t.item
    LEFT JOIN room_item_name n ON n.item = i.id AND n.lang = 'en'
    LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en')
  SELECT coalesce(wt.name, 'floor') AS surface, t.depth, coalesce(n.name, p.name) AS item, t.chain
  FROM tree t JOIN room_item i ON i.id = t.item JOIN room_surface s ON s.id = i.surface
  LEFT JOIN room_wall_text wt ON wt.wall = s.id AND wt.lang = 'en'
  LEFT JOIN room_item_name n ON n.item = i.id AND n.lang = 'en'
  LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en'
  ORDER BY t.sort;

-- every foreign key has an index (sqlite3 .lint fkey-indexes prints nothing): links stay fast as the data grows
CREATE INDEX room_column_wall ON room_column(wall);
CREATE INDEX room_door_product ON room_door(product);
CREATE INDEX room_floor_drain ON room_floor(drain);
CREATE INDEX room_item_name_lang ON room_item_name(lang);
CREATE INDEX room_item_note_lang ON room_item_note(lang);
CREATE INDEX room_item_product ON room_item(product);
CREATE INDEX room_item_surface_fitting ON room_item(surface, fitting);
CREATE INDEX room_label_lang ON room_label(lang);
CREATE INDEX room_lintel_product ON room_lintel(product);
CREATE INDEX room_norm_item ON room_norm(item);
CREATE INDEX room_norm_text_lang ON room_norm_text(lang);
CREATE INDEX room_surface_tile ON room_surface(tile);
CREATE INDEX room_tile_text_lang ON room_tile_text(lang);
CREATE INDEX room_wall_text_lang ON room_wall_text(lang);
