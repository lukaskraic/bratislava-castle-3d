extends Node3D

const MODEL_PATH := "res://models/castle.glb"
const COLLISION_KEYWORDS: PackedStringArray = [
	"Terrain", "Palace", "Building", "Wall", "Stair", "Floor", "Hedge", "Trunk",
]
const HELP := "WASD move, Shift run, Space jump, F fly, Esc mouse, F1 quality, F2 time of day, 0-9 jump to sights"
## Points of interest (Blender coords: x east, y north, z up; eye, look-at) for keys 1-9.
const SIGHTS := [
	["Čestný dvor", Vector3(-14, -80, 2.2), Vector3(-6, -40, 10)],
	["Nádvorie a studňa", Vector3(-12, -15, 1.7), Vector3(19, -7, 2)],
	["Rytierska sála", Vector3(-1.0, -32.5, 1.65), Vector3(22, -34.5, 2.6)],
	["Hlavné schodisko", Vector3(-28.5, 14.7, 7.25), Vector3(-33.8, 15.6, 8.1)],
	["Sála s freskou", Vector3(-1.0, -32.0, 7.3), Vector3(8, -33.5, 8.5)],
	["Korunná veža – vyhliadka", Vector3(-43.2, -33.6, 24.9), Vector3(-43.2, -140, 0)],
	["Suterén", Vector3(-12.5, -30.6, -2.95), Vector3(20, -33, -2.2)],
	["Baroková záhrada", Vector3(28, 95, -2.4), Vector3(2, 10, 14)],
	["Letecký pohľad", Vector3(-170, -150, 110), Vector3(0, 0, 10)],
	["Kaplnka", Vector3(31.97, 12.33, 7.25), Vector3(33.66, 18.79, 7.0)],
]

# Sun presets: name, azimuth (deg, compass direction the sun is in; 0 = north, 90 = east),
# elevation (deg), light energy, color, sky/ambient energy.
const TIMES := [
	{"name": "morning", "az": 100.0, "el": 15.0, "energy": 0.8, "color": Color(1.0, 0.85, 0.7), "sky": 0.8},
	{"name": "noon", "az": 180.0, "el": 60.0, "energy": 1.0, "color": Color(1.0, 0.97, 0.92), "sky": 0.8},
	{"name": "afternoon", "az": 225.0, "el": 35.0, "energy": 0.95, "color": Color(1.0, 0.92, 0.82), "sky": 0.75},
	{"name": "evening", "az": 280.0, "el": 6.0, "energy": 0.7, "color": Color(1.0, 0.6, 0.35), "sky": 0.6},
	{"name": "night", "az": 160.0, "el": 30.0, "energy": 0.06, "color": Color(0.6, 0.7, 1.0), "sky": 0.05},
]

## Add trimesh collision at runtime to named meshes the glTF importer left without a body.
@export var runtime_collision_fallback := true
## glTF point lights arrive with no range (4096 m) and Blender-watt energies; clamp them
## so each light only touches its room.
@export var imported_light_range := 8.0
@export var imported_light_energy := 1.5

@onready var world: Node3D = $World

var player: Player
var sun: DirectionalLight3D
var env: Environment
var sky_mat: ShaderMaterial
var hud: Control
var info_title: Label
var info_rows: Label
var fps_label: Label
var sights_panel: PanelContainer
var toast: Label
var toast_t := 0.0
const QUALITY_NAMES := ["Nízka", "Stredná", "Vysoká", "Ultra"]
const TIME_NAMES := {"morning": "ráno", "noon": "poludnie", "afternoon": "popoludnie", "evening": "večer", "night": "noc"}
## 0 low .. 3 ultra (ultra needs Forward+: SDFGI, SSR); web builds run Compatibility.
var quality := 2
var forward_plus := true
var detail_meshes: Array[MeshInstance3D] = []
var sight_labels: Array[Label] = []
var night_lights: Array[OmniLight3D] = []
## Interior lights from Blender (chandeliers, corridor lamps): off by day, dim warm at night.
var model_lights: Array[Light3D] = []
var emissive_mats: Array[StandardMaterial3D] = []
var high_quality: bool:
	get:
		return quality >= 2
	set(v):
		quality = _max_quality() if v else 0
var time_index := 2
var sight_label := ""


func _ready() -> void:
	forward_plus = RenderingServer.get_current_rendering_method() == "forward_plus"
	quality = 2 if forward_plus else 1
	_register_inputs()
	var spawn := Vector3(0, 2, 0)
	var spawn_node: Node3D

	if ResourceLoader.exists(MODEL_PATH):
		var scene := load(MODEL_PATH) as PackedScene
		var model := scene.instantiate()
		world.add_child(model)
		if runtime_collision_fallback:
			var n := _add_fallback_collision(model)
			print("Runtime collision fallback: %d meshes" % n)
		spawn_node = model.find_child("Spawn", true, false) as Node3D
		# Our own sun drives time of day; an exported Blender sun would double the light.
		for l in model.find_children("*", "DirectionalLight3D", true, false):
			l.queue_free()
		_collect_model_lights(model)
		for l: OmniLight3D in model.find_children("*", "OmniLight3D", true, false):
			l.omni_range = imported_light_range
			l.omni_attenuation = 1.0
			l.light_energy = imported_light_energy
			l.distance_fade_enabled = true
			l.distance_fade_begin = 40.0
			l.distance_fade_length = 10.0
	else:
		print("No %s, building placeholder" % MODEL_PATH)
		spawn_node = _build_placeholder()

	if spawn_node:
		spawn = spawn_node.global_position

	_setup_environment()
	_spawn_night_lights(spawn)

	player = Player.new()
	player.name = "Player"
	player.spawn_position = spawn
	add_child(player)
	player.respawn()

	_setup_hud()
	_apply_quality()
	_apply_time()

	if not OS.get_cmdline_user_args().is_empty():
		var tools: Node = preload("res://scripts/cli_tools.gd").new()
		tools.name = "CliTools"
		add_child(tools)


func _collect_model_lights(model: Node) -> void:
	for n in model.find_children("*", "OmniLight3D", true, false):
		var l := n as OmniLight3D
		l.shadow_enabled = false
		l.omni_range = 7.0
		l.omni_attenuation = 1.5
		l.light_energy = 0.5
		l.light_color = Color(1.0, 0.9, 0.78)
		l.visible = false
		model_lights.append(l)
	for n in model.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if mi.mesh == null:
			continue
		# small details fade out with distance (chunked meshes, so the range is per tile)
		for pair in [["Tufts", 45.0], ["Branches", 160.0], ["Props", 140.0], ["Fountain_Jets", 80.0], ["HedgeLeaves", 70.0]]:
			if mi.name.containsn(pair[0]):
				mi.visibility_range_end = pair[1]
				mi.set_meta("base_range", pair[1])
				detail_meshes.append(mi)
				mi.visibility_range_end_margin = 5.0
				mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		# thin detail (trims, joinery, door leaves, foliage) poisons the SDFGI field -> black artifacts
		for kw in ["Trim", "Windows", "Furnishing", "Props", "Foliage", "Hedges", "Branches", "Garden", "Jets", "Danube", "Tufts", "Smooth", "City_Windows"]:
			if mi.name.containsn(kw):
				mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		for i in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(i) as StandardMaterial3D
			if m:
				m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC   # sharp ground at grazing angles
			if m and (m.resource_name.begins_with("leaves") or m.resource_name.begins_with("grass_tuft")):
				m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
				m.alpha_scissor_threshold = 0.45
				m.cull_mode = BaseMaterial3D.CULL_DISABLED
				m.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE
				m.backlight_enabled = true
				m.backlight = Color(0.35, 0.42, 0.2)
				m.albedo_color = Color(1.0, 1.0, 1.0)
				m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			if m and (m.resource_name == "water" or m.resource_name == "river"):
				var wm := ShaderMaterial.new()
				wm.shader = preload("res://shaders/water.gdshader")
				wm.set_shader_parameter("ripple_a", _ripple_tex(3))
				wm.set_shader_parameter("ripple_b", _ripple_tex(11))
				if m.resource_name == "river":
					wm.set_shader_parameter("scale", 18.0)
					wm.set_shader_parameter("speed", 0.02)
				mi.set_surface_override_material(i, wm)
				continue
			if m and m.resource_name.contains("flag"):
				var fm := ShaderMaterial.new()
				fm.shader = preload("res://shaders/flag.gdshader")
				fm.set_shader_parameter("albedo_tex", m.albedo_texture)
				mi.set_surface_override_material(i, fm)
				continue
			if m and m.emission_enabled and not emissive_mats.has(m):
				emissive_mats.append(m)
	print("Model lights: %d, emissive materials: %d" % [model_lights.size(), emissive_mats.size()])


func _ripple_tex(seed_: int) -> NoiseTexture2D:
	var nt := NoiseTexture2D.new()
	var fn := FastNoiseLite.new()
	fn.seed = seed_
	fn.frequency = 0.02
	fn.fractal_octaves = 3
	nt.noise = fn
	nt.width = 512
	nt.height = 512
	nt.seamless = true
	nt.as_normal_map = true
	nt.bump_strength = 6.0
	return nt


func _register_inputs() -> void:
	var binds := {
		"move_forward": KEY_W, "move_back": KEY_S, "move_left": KEY_A, "move_right": KEY_D,
		"run": KEY_SHIFT, "jump": KEY_SPACE, "crouch": KEY_C, "fly_down": KEY_CTRL,
		"toggle_fly": KEY_F, "quality": KEY_F1, "time_of_day": KEY_F2,
	}
	for action: String in binds:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		var ev := InputEventKey.new()
		ev.physical_keycode = binds[action]
		InputMap.action_add_event(action, ev)


func _has_static_body(node: Node) -> bool:
	for c in node.get_children():
		if c is StaticBody3D:
			return true
	var p := node.get_parent()
	while p:
		if p is CollisionObject3D:
			return true
		p = p.get_parent()
	return false


func _add_fallback_collision(root: Node) -> int:
	var count := 0
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null or _has_static_body(mi):
			continue
		# decorative layers: their structure already collides (walls, floors, invisible rails)
		if mi.name.containsn("Furnishing") or mi.name.containsn("Trim") or mi.name.containsn("Windows") or mi.name.containsn("WallFinish") or mi.name.containsn("HedgeLeaves") or mi.name.containsn("Smooth"):
			continue
		for kw in COLLISION_KEYWORDS:
			if mi.name.containsn(kw):
				mi.create_trimesh_collision()
				count += 1
				break
	return count


func _build_placeholder() -> Node3D:
	var root := Node3D.new()
	root.name = "Placeholder"
	world.add_child(root)

	var stone := StandardMaterial3D.new()
	stone.albedo_color = Color(0.75, 0.72, 0.66)
	var grass := StandardMaterial3D.new()
	grass.albedo_color = Color(0.3, 0.45, 0.2)

	_box(root, "Floor", Vector3(0, -0.5, 0), Vector3(80, 1, 80), grass)

	# Stairs of 0.18 m risers (climbable via step-up, no ramp).
	for i in 10:
		_box(root, "Stair%d" % i, Vector3(6, (i + 1) * 0.09, -4 - i * 0.3), Vector3(3, (i + 1) * 0.18, 0.3), stone)
	_box(root, "Landing", Vector3(6, 0.9, -8.35), Vector3(3, 1.8, 3), stone)

	# 0.3 m step must NOT be climbable (above step_height).
	_box(root, "TooHighStep", Vector3(-6, 0.15, -4), Vector3(3, 0.3, 3), stone)

	# 20 degree ramp.
	var ramp := _box(root, "Ramp", Vector3(-6, 0.9, 6), Vector3(3, 0.2, 6), stone)
	ramp.rotation_degrees.x = 20.0

	# Small room with a window opening, to see SDFGI bounce light.
	var room := CSGCombiner3D.new()
	room.name = "Building"
	room.use_collision = true
	room.position = Vector3(0, 0, 10)
	root.add_child(room)
	_box(room, "Shell", Vector3(0, 2, 0), Vector3(8, 4, 8), stone)
	var hollow := _box(room, "Hollow", Vector3(0, 2.1, 0), Vector3(7.4, 3.8, 7.4), stone)
	hollow.operation = CSGShape3D.OPERATION_SUBTRACTION
	var door := _box(room, "Door", Vector3(0, 1.1, -3.9), Vector3(1.2, 2.2, 1), stone)
	door.operation = CSGShape3D.OPERATION_SUBTRACTION
	var window := _box(room, "Window", Vector3(3.9, 2.2, 0), Vector3(1, 1.4, 2), stone)
	window.operation = CSGShape3D.OPERATION_SUBTRACTION

	_box(root, "WallNorth", Vector3(0, 1.5, -20), Vector3(40, 3, 0.6), stone)

	var spawn := Marker3D.new()
	spawn.name = "Spawn"
	spawn.position = Vector3(0, 0.1, 0)
	root.add_child(spawn)
	return spawn


func _box(parent: Node, n: String, pos: Vector3, size: Vector3, mat: Material) -> CSGBox3D:
	var b := CSGBox3D.new()
	b.name = n
	b.position = pos
	b.size = size
	b.material = mat
	b.use_collision = not (parent is CSGShape3D)
	parent.add_child(b)
	return b


func _setup_environment() -> void:
	sky_mat = ShaderMaterial.new()
	sky_mat.shader = preload("res://shaders/sky.gdshader")
	var sky := Sky.new()
	sky.sky_material = sky_mat

	env = Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.15
	env.tonemap_white = 6.0
	env.ambient_light_sky_contribution = 0.6
	env.sdfgi_energy = 0.7
	env.sdfgi_bounce_feedback = 0.25
	env.sdfgi_use_occlusion = true
	env.sdfgi_cascades = 4
	env.sdfgi_min_cell_size = 0.2
	env.ssao_radius = 1.0
	env.ssao_intensity = 1.5
	env.glow_enabled = true
	env.glow_intensity = 0.12
	env.glow_bloom = 0.0
	env.glow_hdr_threshold = 1.5
	env.fog_enabled = true
	env.fog_light_color = Color(0.7, 0.75, 0.82)
	env.fog_density = 0.0004
	env.fog_aerial_perspective = 0.5
	env.fog_sky_affect = 0.2

	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	sun = DirectionalLight3D.new()
	sun.name = "Sun"
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 300.0
	sun.light_angular_distance = 0.5
	add_child(sun)


func _spawn_night_lights(center: Vector3) -> void:
	for i in 4:
		var l := OmniLight3D.new()
		var a := TAU * i / 4.0 + PI / 4.0
		l.position = center + Vector3(cos(a) * 6.0, 3.0, sin(a) * 6.0)
		l.light_color = Color(1.0, 0.75, 0.45)
		l.light_energy = 2.0
		l.omni_range = 12.0
		l.shadow_enabled = true
		l.visible = false
		add_child(l)
		night_lights.append(l)


func _panel_style(alpha := 0.72) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.08, 0.11, alpha)
	sb.border_color = Color(0.85, 0.7, 0.42, 0.55)
	sb.border_width_left = 3
	sb.set_corner_radius_all(10)
	sb.content_margin_left = 16
	sb.content_margin_right = 16
	sb.content_margin_top = 10
	sb.content_margin_bottom = 10
	sb.shadow_color = Color(0, 0, 0, 0.35)
	sb.shadow_size = 8
	return sb


func _label(text: String, size: int, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _setup_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Control.new()
	hud.set_anchors_preset(Control.PRESET_FULL_RECT)
	hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(hud)
	# info card (top-left)
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style())
	card.position = Vector2(18, 16)
	hud.add_child(card)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 4)
	card.add_child(col)
	info_title = _label("Bratislavský hrad", 20, Color(0.97, 0.9, 0.74))
	col.add_child(info_title)
	info_rows = _label("", 14, Color(0.86, 0.88, 0.9))
	col.add_child(info_rows)
	fps_label = _label("", 11, Color(0.6, 0.64, 0.7))
	col.add_child(fps_label)
	# key hints (bottom-centre)
	var bar := PanelContainer.new()
	bar.add_theme_stylebox_override("panel", _panel_style(0.6))
	bar.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	bar.grow_horizontal = Control.GROW_DIRECTION_BOTH
	bar.grow_vertical = Control.GROW_DIRECTION_BEGIN
	bar.offset_bottom = -16
	hud.add_child(bar)
	var keys := HBoxContainer.new()
	keys.add_theme_constant_override("separation", 14)
	bar.add_child(keys)
	for pair in [["WASD", "pohyb"], ["Shift", "beh"], ["Space", "skok"], ["F", "let"], ["F1", "kvalita"],
			["F2", "denná doba"], ["0–9", "miesta"], ["Tab", "zoznam"], ["H", "skryť"], ["Esc", "myš"]]:
		var chip := HBoxContainer.new()
		chip.add_theme_constant_override("separation", 5)
		var k := PanelContainer.new()
		var ks := StyleBoxFlat.new()
		ks.bg_color = Color(0.85, 0.7, 0.42, 0.9)
		ks.set_corner_radius_all(5)
		ks.content_margin_left = 6
		ks.content_margin_right = 6
		ks.content_margin_top = 1
		ks.content_margin_bottom = 1
		k.add_theme_stylebox_override("panel", ks)
		k.add_child(_label(pair[0], 12, Color(0.08, 0.08, 0.1)))
		chip.add_child(k)
		chip.add_child(_label(pair[1], 12, Color(0.85, 0.87, 0.9)))
		keys.add_child(chip)
	# sights list (right, Tab)
	sights_panel = PanelContainer.new()
	sights_panel.add_theme_stylebox_override("panel", _panel_style())
	sights_panel.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	sights_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	sights_panel.offset_right = -18
	sights_panel.offset_top = 16
	sights_panel.visible = true
	hud.add_child(sights_panel)
	var sl := VBoxContainer.new()
	sights_panel.add_child(sl)
	sl.add_child(_label("Zaujímavé miesta", 16, Color(0.97, 0.9, 0.74)))
	for k2 in SIGHTS.size():
		var sl_lab := _label("%d   %s" % [(k2 + 1) % 10, SIGHTS[k2][0]], 14, Color(0.86, 0.88, 0.9))
		sight_labels.append(sl_lab)
		sl.add_child(sl_lab)
	# toast (centre)
	toast = _label("", 22, Color(0.97, 0.9, 0.74))
	toast.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	toast.add_theme_constant_override("outline_size", 6)
	toast.set_anchors_preset(Control.PRESET_CENTER_TOP)
	toast.grow_horizontal = Control.GROW_DIRECTION_BOTH
	toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast.offset_top = 90
	toast.modulate.a = 0.0
	hud.add_child(toast)


func _toast(text: String) -> void:
	toast.text = text
	toast_t = 1.8


func _max_quality() -> int:
	return 3 if forward_plus else 2


func _apply_quality() -> void:
	var q := clampi(quality, 0, _max_quality())
	quality = q
	var vp := get_viewport()
	vp.scaling_3d_scale = [0.67, 0.85, 1.0, 1.0][q]
	vp.msaa_3d = [Viewport.MSAA_DISABLED, Viewport.MSAA_DISABLED, Viewport.MSAA_2X, Viewport.MSAA_4X][q]
	vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA if q == 1 else Viewport.SCREEN_SPACE_AA_DISABLED
	sun.shadow_enabled = q >= 1
	sun.directional_shadow_max_distance = [60.0, 120.0, 220.0, 320.0][q]
	sun.directional_shadow_mode = (
		DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS if q >= 3
		else (DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS if q == 2 else DirectionalLight3D.SHADOW_ORTHOGONAL)
	)
	env.fog_enabled = q >= 1
	if forward_plus:
		env.sdfgi_enabled = q >= 3
		env.ssao_enabled = q >= 2
		env.ssr_enabled = q >= 3      # reflections in marble, water and glass
		env.ssr_max_steps = 48
		env.ssr_fade_out = 2.0
		env.glow_enabled = q >= 1
	for mi in detail_meshes:
		mi.visibility_range_end = mi.get_meta("base_range") * [0.45, 0.7, 1.0, 1.3][q]


func _apply_time() -> void:
	var t: Dictionary = TIMES[time_index]
	# Godot: -Z = north, +X = east (Blender +Y north survives glTF export as -Z).
	var az := deg_to_rad(t.az)
	var el := deg_to_rad(t.el)
	var to_sun := Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el))
	sun.look_at_from_position(Vector3.ZERO, -to_sun, Vector3.UP)
	sun.light_energy = t.energy
	sun.light_color = t.color
	sky_mat.set_shader_parameter("day", clampf(t.sky / 0.8, 0.0, 1.0))
	var warm: bool = t.name == "evening" or t.name == "morning"
	sky_mat.set_shader_parameter("horizon", Color(1.0, 0.72, 0.52) if warm else Color(0.78, 0.84, 0.9))
	env.ambient_light_energy = maxf(t.sky * 0.45, 0.05)
	var night: bool = t.name == "night"
	sun.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY if night else DirectionalLight3D.SKY_MODE_LIGHT_AND_SKY
	for l in night_lights:
		l.visible = night
	# museum interiors keep chandeliers on by day; windows alone leave deep rooms black
	for l in model_lights:
		var street := l.name.begins_with("L_street")
		l.visible = night or not street
		l.light_energy = (0.75 if street else 1.2) if night else 0.9
		if street:
			l.omni_range = 11.0
	for m in emissive_mats:
		m.emission_energy_multiplier = 1.5 if night else 0.6


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("quality"):
		quality = (quality + 1) % (_max_quality() + 1)
		_apply_quality()
		_toast("Kvalita: " + QUALITY_NAMES[quality])
	elif event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_H:
		hud.visible = not hud.visible
	elif event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_TAB:
		sights_panel.visible = not sights_panel.visible
	elif event.is_action_pressed("time_of_day"):
		time_index = (time_index + 1) % TIMES.size()
		_apply_time()
		_toast("Denná doba: " + TIME_NAMES[TIMES[time_index].name])
	elif event is InputEventKey and event.pressed and not event.echo and event.keycode >= KEY_0 and event.keycode <= KEY_9:
		var s: Array = SIGHTS[9 if event.keycode == KEY_0 else event.keycode - KEY_1]
		var b2g := func(v: Vector3) -> Vector3: return Vector3(v.x, v.z, -v.y)
		player.set_flying(s[0] == "Letecký pohľad")
		player.place_eye(b2g.call(s[1]), b2g.call(s[2]))
		sight_label = s[0]
		for k3 in sight_labels.size():      # highlight the active sight
			sight_labels[k3].add_theme_color_override("font_color", Color(0.98, 0.82, 0.45) if SIGHTS[k3][0] == s[0] else Color(0.86, 0.88, 0.9))
		_toast(s[0])


func _process(delta: float) -> void:
	var p := player.global_position
	info_rows.text = "%s\nKvalita: %s   ·   %s\nRežim: %s" % [
		sight_label if sight_label != "" else "Prechádzka areálom",
		QUALITY_NAMES[quality], TIME_NAMES[TIMES[time_index].name].capitalize(),
		"let" if player.mode_name().to_lower().contains("fly") else "chôdza",
	]
	fps_label.text = "%d FPS   ·   %.0f, %.0f, %.0f m" % [Engine.get_frames_per_second(), p.x, -p.z, p.y]
	if toast_t > 0.0:
		toast_t -= delta
		toast.modulate.a = clampf(toast_t / 0.4, 0.0, 1.0)
