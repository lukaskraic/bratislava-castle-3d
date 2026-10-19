## Parked cars and standing/walking people from CC0 models (godot/models/props, baked by
## scripts/prep_props.py), instanced with one MultiMesh per model.
## Cars: positions from the build (out/street_cars.json, Blender coords [x, y, z, heading]).
## People: scattered beside the walk routes, on level ground the player can see but not in the walking line.
extends Node3D

const CARS := ["car_a", "car_b", "car_suv", "car_hatch", "car_wagon"]
const PEOPLE := ["man", "man_suit", "woman_casual", "woman_dress", "man_walk", "man_suit_walk", "woman_casual_walk", "woman_dress_walk"]
const ROUTE_FILES := ["../data/ref/fortress/descents_waypoints.json", "../out/city_routes.json"]
const PEOPLE_EVERY := 7.0     # m of route per person (on average)

var rng := RandomNumberGenerator.new()


static func b2g(v: Vector3) -> Vector3:
	return Vector3(v.x, v.z, -v.y)


func _ready() -> void:
	rng.seed = 18101
	# the model's colliders must be in the physics space before we raycast
	await get_tree().physics_frame
	await get_tree().physics_frame
	var space := get_world_3d().direct_space_state
	var cars := _load_cars()
	# the build's z samples the road centre; kerb-side lanes sit a little higher (camber), and a ray would hit
	# the car's own invisible collider, so settle the wheels with a fixed lift
	for c in cars:
		var t: Transform3D = c[1]
		t.origin.y += 0.12
		c[1] = t
	var people := _scatter_people(space)
	var nc := _instance(CARS, cars, 260.0)
	var np := _instance(PEOPLE, people, 160.0)
	print("Street life: %d cars, %d people" % [nc, np])


func _mesh_of(name_: String) -> Mesh:
	var path := "res://models/props/%s.glb" % name_
	if not ResourceLoader.exists(path):
		return null
	var root := (load(path) as PackedScene).instantiate()
	var mi := root.find_children("*", "MeshInstance3D", true, false)
	var m: Mesh = (mi[0] as MeshInstance3D).mesh if mi.size() > 0 else null
	root.free()
	return m


func _instance(names: Array, items: Array, vis_end: float) -> int:
	# items: [model_index, Transform3D]
	var n := 0
	for k in names.size():
		var mesh := _mesh_of(names[k])
		if mesh == null:
			continue
		# visibility range is measured to the instance AABB centre, so batch per 100 m cell
		var cells := {}
		for it in items:
			if it[0] != k:
				continue
			var o: Vector3 = it[1].origin
			var key := Vector2i(floori(o.x / 100.0), floori(o.z / 100.0))
			if not cells.has(key):
				cells[key] = []
			cells[key].append(it[1])
		for key in cells:
			var xs: Array = cells[key]
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = mesh
			mm.instance_count = xs.size()
			for i in xs.size():
				mm.set_instance_transform(i, xs[i])
			var mmi := MultiMeshInstance3D.new()
			mmi.name = "StreetLife_%s_%d_%d" % [names[k], key.x, key.y]
			mmi.multimesh = mm
			mmi.visibility_range_end = vis_end
			mmi.visibility_range_end_margin = 20.0
			add_child(mmi)
			n += xs.size()
	return n


## Desktop reads the build outputs next to the project; the web export carries copies in res://data/.
func _open(rel: String) -> FileAccess:
	var packed := "res://data/" + rel.get_file()
	if FileAccess.file_exists(packed):
		return FileAccess.open(packed, FileAccess.READ)
	return FileAccess.open(ProjectSettings.globalize_path("res://").path_join(rel), FileAccess.READ)


func _load_cars() -> Array:
	var out := []
	var f := _open("../out/street_cars.json")
	if f == null:
		return out
	var data = JSON.parse_string(f.get_as_text())
	if not data is Array:
		return out
	for c: Array in data:
		var pos := b2g(Vector3(c[0], c[1], c[2]))
		# Blender heading (CCW from +X) -> Godot yaw about +Y
		var basis := Basis(Vector3.UP, float(c[3]))
		out.append([rng.randi_range(0, CARS.size() - 1), Transform3D(basis, pos)])
	return out


func _scatter_people(space: PhysicsDirectSpaceState3D) -> Array:
	var out := []
	for rf in ROUTE_FILES:
		var f := _open(rf)
		if f == null:
			continue
		var routes: Dictionary = JSON.parse_string(f.get_as_text())
		for rn in routes:
			var pts: Array = routes[rn]
			var acc := 0.0
			for i in range(1, pts.size()):
				var a := b2g(Vector3(pts[i - 1][0], pts[i - 1][1], pts[i - 1][2]))
				var b := b2g(Vector3(pts[i][0], pts[i][1], pts[i][2]))
				var seg := b - a
				seg.y = 0.0
				acc += seg.length()
				if acc < PEOPLE_EVERY * rng.randf_range(0.6, 1.4) or seg.length() < 0.1:
					continue
				acc = 0.0
				var side := seg.normalized().cross(Vector3.UP) * (1.0 if rng.randf() < 0.5 else -1.0)
				var spot := b + side * rng.randf_range(1.3, 2.6) + seg.normalized() * rng.randf_range(-2.0, 2.0)
				var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(spot + Vector3.UP * 2.5, spot + Vector3.DOWN * 4.0))
				var g0 := space.intersect_ray(PhysicsRayQueryParameters3D.create(b + Vector3.UP * 2.5, b + Vector3.DOWN * 4.0))
				# same walking surface as the route: a kerb drop (road) or a step means a different surface
				if hit.is_empty() or g0.is_empty() or (hit.normal as Vector3).y < 0.93 or absf(hit.position.y - g0.position.y) > 0.07:
					continue
				# nobody inside a wall, a tree or behind a parapet: the line from the path must be clear
				var block := space.intersect_ray(PhysicsRayQueryParameters3D.create(b + Vector3.UP * 1.0, hit.position + Vector3.UP * 1.0))
				if not block.is_empty():
					continue
				var k := rng.randi_range(0, PEOPLE.size() - 1)
				# glTF characters face +Z; this yaw turns them to look along the route
				var along := atan2(seg.x, seg.z)
				if k >= 4:     # walkers go up or down the route
					out.append([k, Transform3D(Basis(Vector3.UP, along + (PI if rng.randf() < 0.5 else 0.0)), hit.position)])
				elif rng.randf() < 0.35:     # two people chatting, facing each other
					var p2: Vector3 = hit.position + seg.normalized() * rng.randf_range(0.8, 1.0)
					out.append([k, Transform3D(Basis(Vector3.UP, along), hit.position)])
					out.append([rng.randi_range(0, 3), Transform3D(Basis(Vector3.UP, along + PI), p2)])
				else:
					out.append([k, Transform3D(Basis(Vector3.UP, rng.randf() * TAU), hit.position)])
	return out
