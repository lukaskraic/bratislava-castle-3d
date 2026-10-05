extends Node
## Command-line modes, passed after `--`:
##   --bench               FPS at a few views, High then Low quality
##   --shots <dir>         render the SHOTS list to PNGs
##   --walktest            walk the player along navmesh paths with real collisions
## Positions are Blender coords (x east, y north, z up), converted by b2g().

const SETTLE_SEC := 2.5
const SHOTS := [
	["spawn", null, null],
	["south_gate", Vector3(0, -60, 1.7), Vector3(0, -30, 8)],
	["courtyard", Vector3(-12, -15, 1.7), Vector3(25, 5, 10)],
	["corridor_1f", Vector3(-17.7, -26.1, 7.25), Vector3(14.3, -28.3, 7.1)],
	["room", Vector3(-26.1, -27.8, 7.25), Vector3(-17.9, -34.6, 7.85)],
	["stairs", Vector3(-28.7, 13.6, 7.25), Vector3(-34.0, 14.5, 8.1)],
	["aerial", Vector3(-170, -150, 110), Vector3(0, 0, 10)],
	["match_ref3", Vector3(-38, -78, 2.15), Vector3(-8, -38, 16)],
	["match_ref9", Vector3(28, 95, -2.4), Vector3(2, 10, 14)],
	["east_terrace", Vector3(60, -20, 3.2), Vector3(0, -5, 14)],
	["garden_parterre", Vector3(20, 40, 2.4), Vector3(32, 75, -0.5)],
	["garden_fountain", Vector3(43, 108, 1.0), Vector3(43, 124, 0.5)],
	["knights_hall", Vector3(-1.0, -32.5, 1.65), Vector3(22, -34.5, 2.6)],
	["cellar", Vector3(-12.5, -30.6, -2.95), Vector3(20, -33, -2.2)],
	["state_room", Vector3(-1.0, -32.0, 7.3), Vector3(6, -33.5, 11.5)],
	["skyline", Vector3(-20, -95, 2.5), Vector3(330, -400, 20)],
	["chapel", Vector3(31.97, 12.33, 7.25), Vector3(33.66, 18.79, 7.0)],
	["crown_view", Vector3(-43.2, -33.6, 24.9), Vector3(-43.2, -140, 0)],
]
# Each leg: name, list of Blender goals walked in order.
const WALK_LEGS := [
	["a_gate_to_courtyard", [
		Vector3(-6, -44, 0), Vector3(-6, -38, 0), Vector3(-6, -33, 0), Vector3(-6, -26, 0),
		Vector3(-2, -20, 0),
	]],
	["b_west_wing_stairs", [
		Vector3(5, 0, 0), Vector3(-2, -20, 0), Vector3(-27.3, -0.6, 0), Vector3(-31, 14, 0),
		Vector3(-28.7, 13.6, 5.6), Vector3(-28.7, 13.6, 11.2),
	]],
	["c_crown_tower", [
		Vector3(-28.7, 13.6, 16.6), Vector3(-27.74, 14.57, 16.6), Vector3(-24.98, 14.09, 16.6),
		Vector3(-29.82, -15.0, 16.6), Vector3(-31.26, -22.15, 16.6), Vector3(-34.31, -21.63, 16.6),
		Vector3(-42.14, -24.07, 16.6), Vector3(-42.55, -26.44, 16.6), Vector3(-39.9, -27.6, 16.6), Vector3(-39.8, -31.6, 16.6),
		Vector3(-41.7, -30.6, 16.75),
		Vector3(-41.99, -29.53, 16.97), Vector3(-42.50, -29.02, 17.24), Vector3(-43.20, -28.83, 17.50), Vector3(-43.90, -29.02, 17.77), Vector3(-44.41, -29.53, 18.04), Vector3(-44.60, -30.23, 18.31), Vector3(-44.41, -30.93, 18.57), Vector3(-43.90, -31.44, 18.84), Vector3(-43.20, -31.63, 19.11), Vector3(-42.50, -31.44, 19.38), Vector3(-41.99, -30.93, 19.64), Vector3(-41.80, -30.23, 19.91), Vector3(-41.99, -29.53, 20.18), Vector3(-42.50, -29.02, 20.45), Vector3(-43.20, -28.83, 20.71), Vector3(-43.90, -29.02, 20.98), Vector3(-44.41, -29.53, 21.25), Vector3(-44.60, -30.23, 21.52), Vector3(-44.41, -30.93, 21.78), Vector3(-43.90, -31.44, 22.05), Vector3(-43.20, -31.63, 22.32), Vector3(-42.50, -31.44, 22.59), Vector3(-41.99, -30.93, 22.85), Vector3(-41.80, -30.23, 23.12),
		Vector3(-39.75, -30.2, 23.05), Vector3(-40.1, -26.9, 23.05), Vector3(-43.2, -26.55, 23.05), Vector3(-46.6, -27.5, 23.05),
	]],
]
const NAV_AABB := AABB(Vector3(-70, -4, -50), Vector3(125, 32, 105))
const STUCK_SEC := 4.0

@onready var main: Node3D = get_parent()
var _region: RID


static func b2g(v: Vector3) -> Vector3:
	return Vector3(v.x, v.z, -v.y)


static func g2b(v: Vector3) -> Vector3:
	return Vector3(v.x, -v.z, v.y)


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	get_tree().create_timer(900.0).timeout.connect(func() -> void:
		push_error("CLI mode watchdog timeout")
		get_tree().quit(1))
	await get_tree().process_frame
	if "--bench" in args:
		await _bench()
	elif "--shots" in args:
		var i := args.find("--shots")
		var dir := args[i + 1] if i + 1 < args.size() else "user://shots"
		await _shots(dir)
	elif "--sighttest" in args:
		await _sighttest()
	elif "--walktest" in args:
		await _walktest()
	get_tree().quit()


func _wait(sec: float) -> void:
	await get_tree().create_timer(sec).timeout


func _spawn_view() -> Array:
	var eye: Vector3 = main.player.spawn_position + Vector3.UP * Player.EYE_HEIGHT
	return [eye, Vector3(0, 8, 0)]


func _bench() -> void:
	var views := {
		"spawn": _spawn_view(),
		"courtyard": [b2g(Vector3(-12, -15, 1.7)), b2g(Vector3(25, 5, 10))],
		"aerial": [b2g(Vector3(-170, -150, 110)), b2g(Vector3(0, 0, 10))],
	}
	main.player.set_flying(true)
	for q in [true, false]:
		main.high_quality = q
		main._apply_quality()
		for v in views:
			main.player.place_eye(views[v][0], views[v][1])
			await _wait(2.0)
			var frames := 0
			var worst := 0.0
			var t0 := Time.get_ticks_usec()
			var last := t0
			while Time.get_ticks_usec() - t0 < 4_000_000:
				await get_tree().process_frame
				var now := Time.get_ticks_usec()
				worst = maxf(worst, (now - last) / 1000.0)
				last = now
				frames += 1
			var avg := frames / ((last - t0) / 1e6)
			var draws := RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)
			print("BENCH %s %-9s avg %.1f fps, worst frame %.1f ms, draw calls %d" % [
				"High" if q else "Low ", v, avg, worst, draws])


func _shots(dir: String) -> void:
	DirAccess.make_dir_recursive_absolute(dir)
	main.hud.visible = false
	main.player.set_flying(true)
	var probes := _probe_shots()
	for s0 in SHOTS:
		var s: Array = s0
		if probes.has(s[0]):
			s = [s[0], probes[s[0]][0], probes[s[0]][1]]
		var eye: Vector3
		var target: Vector3
		if s[1] == null:
			var sv := _spawn_view()
			eye = sv[0]
			target = sv[1]
		else:
			eye = b2g(s[1])
			target = b2g(s[2])
		main.player.place_eye(eye, target)
		await _wait(SETTLE_SEC)
		await RenderingServer.frame_post_draw
		var path := dir.path_join("%s.png" % s[0])
		var err := get_viewport().get_texture().get_image().save_png(path)
		print("SHOT %s -> %s (%s)" % [s[0], path, error_string(err)])
	# UI check: spawn view with the HUD, sights list and a toast
	main.hud.visible = true
	main.sights_panel.visible = true
	main._toast("Kvalita: " + main.QUALITY_NAMES[main.quality])
	var sv0 := _spawn_view()
	main.player.place_eye(sv0[0], sv0[1])
	await _wait(1.0)
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(dir.path_join("hud.png"))
	main.hud.visible = false
	main.sights_panel.visible = false
	# night variants of a few views (street lamps, chandeliers)
	main.time_index = 4
	main._apply_time()
	for s0 in SHOTS:
		if not (s0[0] in ["spawn", "courtyard", "knights_hall"]):
			continue
		var s: Array = s0
		var eye: Vector3
		var target: Vector3
		if s[1] == null:
			var sv := _spawn_view()
			eye = sv[0]
			target = sv[1]
		else:
			eye = b2g(s[1])
			target = b2g(s[2])
		main.player.place_eye(eye, target)
		await _wait(SETTLE_SEC)
		await RenderingServer.frame_post_draw
		var npath := dir.path_join("night_%s.png" % s[0])
		get_viewport().get_texture().get_image().save_png(npath)
		print("SHOT night_%s" % s[0])


func _bake_navmesh() -> RID:
	var nm := NavigationMesh.new()
	nm.agent_radius = Player.RADIUS
	nm.agent_height = Player.HEIGHT
	nm.agent_max_climb = 0.25
	nm.agent_max_slope = 50.0
	nm.cell_size = 0.25
	nm.cell_height = 0.1
	nm.region_min_size = 4.0
	nm.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	nm.filter_baking_aabb = NAV_AABB
	var src := NavigationMeshSourceGeometryData3D.new()
	var t0 := Time.get_ticks_msec()
	NavigationServer3D.parse_source_geometry_data(nm, src, main.world)
	NavigationServer3D.bake_from_source_geometry_data(nm, src)
	print("NAV baked in %d ms, %d polygons" % [Time.get_ticks_msec() - t0, nm.get_polygon_count()])
	var map: RID = main.get_world_3d().navigation_map
	_region = NavigationServer3D.region_create()
	NavigationServer3D.region_set_map(_region, map)
	NavigationServer3D.region_set_navigation_mesh(_region, nm)
	NavigationServer3D.map_force_update(map)
	await get_tree().physics_frame
	await get_tree().physics_frame
	return map


func _walktest() -> void:
	main.hud.visible = false
	var map := await _bake_navmesh()
	var p: Player = main.player
	p.respawn()
	print("SPAWN %s" % _fmt(p.spawn_position))
	await _wait(0.5)
	var ok_all := true
	for leg in _legs():
		print("LEG %s from %s" % [leg[0], _fmt(p.global_position)])
		if String(leg[0]).ends_with("@tp"):     # start this leg at its first waypoint (independent route)
			p.global_position = b2g(leg[1][0]) + Vector3.UP * 0.3
			p.velocity = Vector3.ZERO
			await _wait(0.5)
		for goal_b: Vector3 in leg[1]:
			var goal := NavigationServer3D.map_get_closest_point(map, b2g(goal_b))
			# navmesh snaps helix points onto another turn of the spiral; walk to the raw point then
			if goal.distance_to(b2g(goal_b)) > 0.8:
				goal = b2g(goal_b) + Vector3.UP * 0.2
			var path := NavigationServer3D.map_get_path(map, p.global_position, goal, true)
			var nav_end := path[path.size() - 1] if path.size() > 0 else p.global_position
			if nav_end.distance_to(goal) > 1.0:
				print("  NAV gap: no navmesh path to %s, closest reachable %s" % [_fmt(goal), _fmt(nav_end)])
				_probe(nav_end, goal)
			var res := await _follow(p, path)
			var reached := p.global_position.distance_to(goal) < 1.0
			if not reached:
				# Navmesh is conservative (cell erosion); check whether physics lets us through anyway.
				var direct := await _follow(p, PackedVector3Array([p.global_position, goal]))
				reached = p.global_position.distance_to(goal) < 1.0
				res += " | straight-line: %s" % ("ok" if reached else direct)
			ok_all = ok_all and reached
			print("  %s goal %s (asked %s): pos %s %s" % [
				"REACHED" if reached else "FAILED ", _fmt(goal), goal_b, _fmt(p.global_position), res])
			if not reached:
				# Teleport past the blockage so later goals (e.g. the stairs) still get tested.
				p.global_position = goal + Vector3.UP * 0.1
				p.velocity = Vector3.ZERO
				print("  TELEPORTED to goal")
				await _wait(0.5)
	Input.action_release("move_forward")
	Input.action_release("run")
	print("WALKTEST %s" % ("PASS" if ok_all else "FAIL"))
	NavigationServer3D.free_rid(_region)


# Steer along path points with the normal walk controller; returns "" or a stuck report.
func _follow(p: Player, path: PackedVector3Array) -> String:
	Input.action_press("run")
	var i := 1
	var best := INF
	var best_t := Time.get_ticks_msec()
	var last_hit := "none"
	while i < path.size():
		var target := path[i]
		var flat := Vector2(target.x - p.global_position.x, target.z - p.global_position.z)
		if flat.length() < 0.4 and absf(target.y - p.global_position.y) < 1.2:
			i += 1
			best = INF
			best_t = Time.get_ticks_msec()
			continue
		p.face(target)
		Input.action_press("move_forward")
		await get_tree().physics_frame
		for c in p.get_slide_collision_count():
			var col := p.get_slide_collision(c)
			if col.get_normal().y < 0.7:
				var obj := col.get_collider() as Node
				var owner_name: String = obj.get_parent().name if obj and obj.get_parent() else "?"
				last_hit = "%s/%s at %s n=%s" % [owner_name, String(obj.name) if obj else "?",
					_fmt(col.get_position()), col.get_normal().snappedf(0.01)]
		if p.global_position.y < -20.0:
			Input.action_release("move_forward")
			return "FELL at %s" % _fmt(p.global_position)
		var d := flat.length()
		if d < best - 0.2:
			best = d
			best_t = Time.get_ticks_msec()
		elif Time.get_ticks_msec() - best_t > STUCK_SEC * 1000:
			Input.action_release("move_forward")
			return "STUCK at %s heading to path pt %s (%d/%d), last wall hit: %s" % [
				_fmt(p.global_position), _fmt(target), i, path.size() - 1, last_hit]
	Input.action_release("move_forward")
	await _wait(0.3)
	return ""


# Rays along the straight line at knee/chest/head height name what blocks a navmesh gap.
func _probe(from: Vector3, to: Vector3) -> void:
	var space: PhysicsDirectSpaceState3D = main.get_world_3d().direct_space_state
	for h in [0.3, 1.0, 1.6]:
		var q := PhysicsRayQueryParameters3D.create(from + Vector3.UP * h, to + Vector3.UP * h)
		q.exclude = [main.player.get_rid()]
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			print("    ray h=%.1f: clear" % h)
		else:
			var obj: Node = hit.collider
			print("    ray h=%.1f: blocked by %s/%s at %s n=%s" % [h, obj.get_parent().name, obj.name,
				_fmt(hit.position), (hit.normal as Vector3).snappedf(0.01)])


# Prints Blender coordinates so geometry fixes can be made directly in Blender.
func _fmt(g: Vector3) -> String:
	var b := g2b(g)
	return "B(%.1f, %.1f, %.2f)" % [b.x, b.y, b.z]

## Walk legs; the Crown Tower leg is rebuilt from out/probes.json (exported by the Blender
## generator) so waypoints follow the geometry when the palace layout changes.
func _legs() -> Array:
	var legs: Array = WALK_LEGS.duplicate(true)
	var f := FileAccess.open(ProjectSettings.globalize_path("res://").path_join("../out/probes.json"), FileAccess.READ)
	if f == null:
		return legs
	var nav: Dictionary = JSON.parse_string(f.get_as_text()).get("nav", {})
	if not nav.has("crown_center"):
		return legs
	var z3 := 16.6
	var v := func(a: Array, z: float) -> Vector3: return Vector3(a[0], a[1], z)
	var ring: Array = nav["corr_ring"]
	var pts: Array = [v.call(nav["stair_door_room"], z3), v.call(nav["stair_door_corr"], z3)]
	pts.append((v.call(ring[3], z3) + v.call(ring[0], z3)) * 0.5)
	pts.append(v.call(nav["sw_corner_door_corr"], z3))
	pts.append(v.call(nav["sw_corner_door_room"], z3))
	var door: Array = nav["crown_doors"][nav["crown_doors"].size() - 1]
	pts.append(v.call(door[0], z3))
	pts.append(v.call(door[1], z3))
	var c: Array = nav["crown_center"]
	var cx: float = c[0]
	var cy: float = c[1]
	pts.append(Vector3(cx + 3.3, cy + 2.2, z3))
	pts.append(Vector3(cx + 3.4, cy - 1.4, z3))
	pts.append(Vector3(cx + 1.5, cy - 0.4, z3 + 0.15))
	for k in range(1, 25):
		var a := k * PI / 6.0
		pts.append(Vector3(cx + 1.4 * cos(a), cy + 1.4 * sin(a), z3 + (23.02 - z3) * k / 24.0 + 0.1))
	pts.append(Vector3(cx + 3.45, cy, 23.05))
	for i in legs.size():
		if legs[i][0] == "c_crown_tower":
			legs[i] = ["c_crown_tower", pts]
	if nav.has("gate_N_out"):
		var gz: float = 0.0
		legs.append(["e_north_gate_to_garden@tp", [Vector3(5, 0, 0), v.call(nav["gate_N_in"], gz), v.call(nav["gate_N_out"], gz),
			v.call(nav["gate_N_out"], gz) + Vector3(0, 8, 0), Vector3(43, 112, -4.0)]])
	if nav.has("cellar_top"):
		var cel: Array = [Vector3(-2.0, -20.0, 0.0), v.call(nav["cellar_room_corr"], 0.0), v.call(nav["cellar_room_in"], 0.0),
			v.call(nav["cellar_top"], 0.0), v.call(nav["cellar_step1"], -0.1)]
		var s1: Vector3 = v.call(nav["cellar_step1"], -0.1)
		var lo: Vector3 = v.call(nav["cellar_low"], -4.4)
		for k in range(1, 9):
			cel.append(s1.lerp(lo, k / 8.0))
		cel.append(v.call(nav["cellar_bottom"], -4.6))
		var back: Array = cel.slice(1, cel.size() - 1)
		back.reverse()
		cel.append_array(back)      # and climb back out to the courtyard
		legs.insert(1, ["d_cellar", cel])
	return legs


## Interior shot cameras exported by the Blender generator (they move with the layout).
func _probe_shots() -> Dictionary:
	var out := {}
	var f := FileAccess.open(ProjectSettings.globalize_path("res://").path_join("../out/probes.json"), FileAccess.READ)
	if f == null:
		return out
	var d: Dictionary = JSON.parse_string(f.get_as_text())
	for pair in [["room", "interior_room"], ["corridor_1f", "interior_corridor"], ["stairs", "stairs"]]:
		if d.has(pair[1]):
			var e: Array = d[pair[1]][0]
			var t: Array = d[pair[1]][1]
			out[pair[0]] = [Vector3(e[0], e[1], e[2]), Vector3(t[0], t[1], t[2])]
	return out


## Teleport to every sight and check the player stays on the floor (no falling off edges).
func _sighttest() -> void:
	var ok := true
	for i in main.SIGHTS.size():
		main.goto_sight(i)
		var y0: float = main.player.global_position.y
		await _wait(3.0)
		var dy: float = main.player.global_position.y - y0
		var good: bool = absf(dy) < 1.0 or main.player.flying
		ok = ok and good
		print("SIGHT %-26s y %.2f -> %.2f %s" % [main.SIGHTS[i][0], y0, main.player.global_position.y, "OK" if good else "FELL"])
	print("SIGHTTEST %s" % ("PASS" if ok else "FAIL"))
