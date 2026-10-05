class_name Player
extends CharacterBody3D

@export var walk_speed := 1.6
@export var run_speed := 4.5
@export var crouch_speed := 0.9
@export var fly_speed := 8.0
@export var fly_fast_speed := 30.0
@export var jump_velocity := 3.8
@export var mouse_sensitivity := 0.0025
@export var step_height := 0.25
@export var kill_y := -100.0

const RADIUS := 0.3
const HEIGHT := 1.75
const EYE_HEIGHT := 1.65
const CROUCH_HEIGHT := 1.1
const CROUCH_EYE := 1.0

var spawn_position := Vector3(0, 2, 0)
var flying := false
var crouching := false
var running := false

var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var _camera: Camera3D
var _shape: CollisionShape3D
var _capsule: CapsuleShape3D
var _eye := EYE_HEIGHT
var _eye_target := EYE_HEIGHT
var _step_offset := 0.0


func _ready() -> void:
	_capsule = CapsuleShape3D.new()
	_capsule.radius = RADIUS
	_capsule.height = HEIGHT
	_shape = CollisionShape3D.new()
	_shape.shape = _capsule
	_shape.position.y = HEIGHT * 0.5
	add_child(_shape)

	_camera = Camera3D.new()
	_camera.position.y = EYE_HEIGHT
	_camera.fov = 75.0
	_camera.near = 0.05
	_camera.far = 4000.0
	add_child(_camera)
	_camera.make_current()

	floor_snap_length = 0.4
	floor_max_angle = deg_to_rad(50.0)
	floor_constant_speed = true
	floor_stop_on_slope = true
	safe_margin = 0.01
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func respawn() -> void:
	global_position = spawn_position
	velocity = Vector3.ZERO


func set_flying(on: bool) -> void:
	flying = on
	_shape.disabled = on
	velocity = Vector3.ZERO


func place_eye(eye: Vector3, target: Vector3) -> void:
	global_position = eye - Vector3.UP * _eye
	var d := target - eye
	rotation.y = atan2(-d.x, -d.z)
	_camera.rotation.x = atan2(d.y, Vector2(d.x, d.z).length())
	_step_offset = 0.0


func face(target: Vector3) -> void:
	var d := target - global_position
	rotation.y = atan2(-d.x, -d.z)


func mode_name() -> String:
	if flying:
		return "FLY"
	if crouching:
		return "crouch"
	return "run" if running else "walk"


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		_camera.rotate_x(-event.relative.y * mouse_sensitivity)
		_camera.rotation.x = clampf(_camera.rotation.x, deg_to_rad(-89), deg_to_rad(89))
	elif event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event.is_action_pressed("toggle_fly"):
		flying = not flying
		_shape.disabled = flying
		velocity = Vector3.ZERO
	elif event.is_action_pressed("crouch") and not flying:
		_set_crouch(not crouching)


func _set_crouch(on: bool) -> void:
	if not on and test_move(global_transform, Vector3.UP * (HEIGHT - CROUCH_HEIGHT)):
		return  # no headroom to stand up
	crouching = on
	var h := CROUCH_HEIGHT if on else HEIGHT
	_capsule.height = h
	_shape.position.y = h * 0.5
	_eye_target = CROUCH_EYE if on else EYE_HEIGHT


func _physics_process(delta: float) -> void:
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var dir := (global_basis * Vector3(input.x, 0, input.y)).normalized()
	running = Input.is_action_pressed("run")

	if flying:
		_fly(delta, input)
	else:
		_walk(delta, dir)

	if global_position.y < kill_y:
		respawn()

	# Camera smoothing so step-ups and crouching don't snap the view.
	_eye = move_toward(_eye, _eye_target, delta * 4.0)
	_step_offset = lerpf(_step_offset, 0.0, 1.0 - exp(-12.0 * delta))
	_camera.position.y = _eye - _step_offset


func _fly(delta: float, input: Vector2) -> void:
	var cam_basis := _camera.global_basis
	var v := cam_basis * Vector3(input.x, 0, input.y)
	if Input.is_action_pressed("jump"):
		v += Vector3.UP
	if Input.is_action_pressed("fly_down"):
		v += Vector3.DOWN
	var speed := fly_fast_speed if running else fly_speed
	global_position += v.normalized() * speed * delta


func _walk(delta: float, dir: Vector3) -> void:
	if not is_on_floor():
		velocity.y -= _gravity * delta
	elif Input.is_action_just_pressed("jump") and not crouching:
		velocity.y = jump_velocity

	var speed := crouch_speed if crouching else (run_speed if running else walk_speed)
	var accel := 12.0 if is_on_floor() else 2.0
	var target := dir * speed
	velocity.x = move_toward(velocity.x, target.x, accel * speed * delta)
	velocity.z = move_toward(velocity.z, target.z, accel * speed * delta)

	if is_on_floor() and velocity.y <= 0.0:
		_try_step_up(delta)
	move_and_slide()


# Climb a step of up to step_height: if blocked horizontally, test up -> forward -> down
# and teleport onto the step top when it is walkable floor.
func _try_step_up(delta: float) -> void:
	var h := Vector3(velocity.x, 0, velocity.z) * delta
	if h.length_squared() < 1e-8:
		return
	# Probe a bit further than one frame so the capsule edge clears the step lip.
	var probe := h.normalized() * maxf(h.length(), RADIUS * 0.5)
	if not test_move(global_transform, probe):
		return

	var params := PhysicsTestMotionParameters3D.new()
	var result := PhysicsTestMotionResult3D.new()
	params.margin = safe_margin
	var t := global_transform

	params.from = t
	params.motion = Vector3.UP * step_height
	var rise := step_height
	if PhysicsServer3D.body_test_motion(get_rid(), params, result):
		rise = result.get_travel().y
	if rise <= 0.01:
		return
	t.origin.y += rise

	params.from = t
	params.motion = probe
	if PhysicsServer3D.body_test_motion(get_rid(), params, result):
		return  # wall, not a step
	t.origin += probe

	params.from = t
	params.motion = Vector3.DOWN * (rise + 0.02)
	if not PhysicsServer3D.body_test_motion(get_rid(), params, result):
		return
	if result.get_collision_normal().angle_to(Vector3.UP) > floor_max_angle:
		return
	t.origin += result.get_travel()
	var dy := t.origin.y - global_position.y
	if dy < 0.01:
		return
	global_position.y += dy
	_step_offset += dy
