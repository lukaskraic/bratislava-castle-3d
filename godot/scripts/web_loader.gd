## Web build: the castle starts from the main pack; the Old Town follows as extra resource packs listed in
## res://web_packs.json ({"packs": [{"file": "city_0.pck", "bytes": N, "scene": "res://models/city_0.glb"}]}).
## Each pack is downloaded next to index.html, mounted with load_resource_pack and handed to main.gd.
extends Node

signal pack_ready(scene_path: String)
signal all_done

var packs: Array = []
var total_bytes := 0
var done_bytes := 0
var http: HTTPRequest
var current := -1
var base_url := ""
var bar: ProgressBar
var label: Label
var panel: PanelContainer
var prefetching := false


func _ready() -> void:
	var f := FileAccess.open("res://web_packs.json", FileAccess.READ)
	packs = (JSON.parse_string(f.get_as_text()) as Dictionary).get("packs", [])
	for p in packs:
		total_bytes += int(p.get("bytes", 0))
	if OS.has_feature("web"):
		base_url = str(JavaScriptBridge.eval("window.location.href.split('?')[0].replace(/[^/]*$/, '')"))
	_build_ui()
	http = HTTPRequest.new()
	http.use_threads = false
	http.download_chunk_size = 16777216     # the default 64 KiB per frame takes ~1000 frames for one pack
	# GitHub Pages gzips .pck; the browser's fetch already inflates it, so a second inflate in Godot fails
	http.accept_gzip = false
	add_child(http)
	http.request_completed.connect(_on_completed)
	_next()


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 20
	add_child(layer)
	panel = PanelContainer.new()
	panel.anchor_left = 0.5
	panel.anchor_right = 0.5
	panel.anchor_top = 1.0
	panel.anchor_bottom = 1.0
	panel.offset_left = -220
	panel.offset_right = 220
	panel.offset_top = -150
	panel.offset_bottom = -88
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.07, 0.09, 0.72)
	sb.set_corner_radius_all(8)
	sb.content_margin_left = 14
	sb.content_margin_right = 14
	sb.content_margin_top = 8
	sb.content_margin_bottom = 10
	panel.add_theme_stylebox_override("panel", sb)
	layer.add_child(panel)
	var box := VBoxContainer.new()
	panel.add_child(box)
	label = Label.new()
	label.add_theme_font_size_override("font_size", 15)
	label.add_theme_color_override("font_color", Color(0.92, 0.92, 0.9))
	box.add_child(label)
	bar = ProgressBar.new()
	bar.min_value = 0
	bar.max_value = 100
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0, 8)
	box.add_child(bar)


func _next() -> void:
	current += 1
	if current >= packs.size():
		label.text = "Mesto načítané"
		bar.value = 100
		all_done.emit()
		var t := get_tree().create_timer(3.0)
		t.timeout.connect(panel.hide)
		return
	var p: Dictionary = packs[current]
	if OS.has_feature("web"):
		# Godot's HTTPRequest only sees the body once fetch() has it all; a streaming fetch in JS reports real
		# progress and warms the browser cache, so the HTTPRequest below is then served locally
		prefetching = true
		JavaScriptBridge.eval("""(function(u){ window.__gpk = {got: 0, done: false, ok: false};
			fetch(u).then(function(r){ var rd = r.body.getReader();
				function pump(){ return rd.read().then(function(x){ if (x.done) { window.__gpk.done = true; window.__gpk.ok = r.ok; return; }
					window.__gpk.got += x.value.length; return pump(); }); }
				return pump(); }).catch(function(){ window.__gpk.done = true; }); })('%s')""" % (base_url + str(p["file"])))
	else:
		_fetch()


func _fetch() -> void:
	var p: Dictionary = packs[current]
	var err := http.request(base_url + str(p["file"]))
	if err != OK:
		label.text = "Mesto sa nepodarilo načítať (%d)" % err
		push_error("web pack request failed: %d" % err)


func _process(_delta: float) -> void:
	if current < 0 or current >= packs.size():
		return
	var got := done_bytes + http.get_downloaded_bytes()
	if prefetching:
		got = done_bytes + int(JavaScriptBridge.eval("window.__gpk ? window.__gpk.got : 0"))
		if bool(JavaScriptBridge.eval("window.__gpk && window.__gpk.done")):
			prefetching = false
			_fetch()
	var pct := 100.0 * got / maxf(1.0, float(total_bytes))
	bar.value = pct
	label.text = "Načítavam Staré Mesto a nábrežie… %d %%  (%d / %d MB)" % [int(pct), got / 1048576, total_bytes / 1048576]


func _on_completed(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var p: Dictionary = packs[current]
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		label.text = "Mesto sa nepodarilo načítať (HTTP %d)" % code
		push_error("web pack %s failed: result %d, HTTP %d" % [p["file"], result, code])
		return
	done_bytes += int(p.get("bytes", 0))
	label.text = "Pripravujem %s…" % str(p.get("label", "mesto"))
	await get_tree().process_frame
	# HTTPRequest.download_file does not write on the web platform: keep the body and store it ourselves
	var path := "user://" + str(p["file"])
	var fa := FileAccess.open(path, FileAccess.WRITE)
	if fa == null:
		push_error("cannot write %s: %d" % [path, FileAccess.get_open_error()])
		return
	fa.store_buffer(body)
	fa.close()
	print("web pack %s: %d bytes" % [p["file"], body.size()])
	body = PackedByteArray()
	if not ProjectSettings.load_resource_pack(path, false):
		push_error("load_resource_pack failed: " + str(p["file"]))
	else:
		pack_ready.emit(str(p["scene"]))
	await get_tree().process_frame
	_next()
