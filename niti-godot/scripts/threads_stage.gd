extends Node2D
## Standalone generative audiovisual *visual* study; no lyrics or music master embedded.
## 106 BPM is a project reference only: no unverified lyric-time synchronization.
## Toggle fear/release with Space or screen tap. R resets elapsed visual time.

const WIDTH := 1280.0
const HEIGHT := 720.0
const THREAD_COUNT := 52
const SAMPLES := 44
const BLUE_DARK := Color(0.027, 0.040, 0.071, 1.0)
const BLUE_LIGHT := Color(0.24, 0.40, 0.56, 1.0)
const WARM := Color(0.95, 0.70, 0.41, 1.0)
const PALE := Color(0.91, 0.91, 0.85, 1.0)

@export var relief: bool = false
@export var movement_strength: float = 1.0
@export var animated_transition: bool = true

var frame_index: int = 0
var blend: float = 0.0
var pointer: Vector2 = Vector2(640.0, 360.0)
var pointer_active: bool = false
var preview_mode: bool = false

func _ready() -> void:
    preview_mode = OS.get_environment("NITI_RENDER_PREVIEW") == "1"
    if OS.get_environment("NITI_PREVIEW_RELIEF") == "1":
        relief = true
    blend = 1.0 if relief else 0.0
    set_process(true)
    queue_redraw()

func _process(delta: float) -> void:
    # Fixed-frame preview under Godot --write-movie --fixed-fps; no wall-clock dependence.
    frame_index += 1
    if animated_transition:
        var target := 1.0 if relief else 0.0
        blend = move_toward(blend, target, delta * 0.62)
    else:
        blend = 1.0 if relief else 0.0
    queue_redraw()

func _unhandled_input(event: InputEvent) -> void:
    if preview_mode:
        return
    if event is InputEventMouseMotion:
        pointer = get_global_mouse_position()
        pointer_active = true
    elif event is InputEventMouseButton:
        if event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
            relief = not relief
    elif event is InputEventScreenTouch:
        if event.pressed:
            pointer = event.position
            relief = not relief
            pointer_active = true
    elif event is InputEventKey:
        if event.pressed and not event.echo:
            if event.keycode == KEY_SPACE:
                relief = not relief
            elif event.keycode == KEY_R:
                frame_index = 0

func _draw() -> void:
    var rect := get_viewport_rect()
    var stretch := Vector2(rect.size.x / WIDTH, rect.size.y / HEIGHT)
    draw_set_transform(Vector2.ZERO, 0.0, stretch)
    draw_rect(Rect2(0, 0, WIDTH, HEIGHT), BLUE_DARK, true)
    var t := float(frame_index) / 24.0
    _draw_haze(t)
    _draw_threads(t)
    _draw_center(t)
    draw_set_transform(Vector2.ZERO)

func _draw_haze(t: float) -> void:
    for layer in range(9):
        var radius := 160.0 + float(layer) * 75.0
        var fade := 1.0 - float(layer) / 10.0
        var c := BLUE_LIGHT.lerp(WARM, blend * 0.72)
        c.a = (0.008 + blend * 0.008) * fade
        draw_circle(Vector2(660.0, 340.0), radius + sin(t * 0.28 + layer) * 6.0, c)
    for dot_id in range(80):
        var seed := float(dot_id) * 2.399963
        var pos := Vector2(
            fposmod(float(dot_id * 173 + 79), WIDTH),
            fposmod(float(dot_id * 311 + 47), HEIGHT)
        )
        var opacity := 0.07 + 0.06 * sin(t * 0.4 + seed)
        draw_circle(pos, 0.7 + 0.6 * blend, Color(0.76, 0.82, 0.89, opacity))

func _draw_threads(t: float) -> void:
    # Threads connect opposite sides. In fear they knot and constrict;
    # in release, they separate into breathing, lightly curved paths.
    for i in range(THREAD_COUNT):
        var index := float(i)
        var spread := index / float(THREAD_COUNT - 1)
        var start := Vector2(-40.0, 72.0 + index * 11.6)
        var finish := Vector2(1320.0, 70.0 + index * 11.6)
        var pts := PackedVector2Array()
        for step in range(SAMPLES + 1):
            var u := float(step) / float(SAMPLES)
            var x := lerpf(start.x, finish.x, u)
            var tightness := pow(maxf(0.0, 1.0 - absf(u - 0.5) * 2.0), 2.0)
            var cramped := lerpf(start.y, finish.y, u) + (360.0 - lerpf(start.y, finish.y, u)) * tightness * (1.0 - blend) * 0.93
            var open_wave := sin(u * PI * 2.0 + index * 0.105 + t * 0.38) * (17.0 + 12.0 * blend) * tightness
            var restless := sin(u * 17.0 + t * 0.64 + index * 0.31) * 3.6 * (1.0 - blend) * tightness
            var y := lerpf(cramped, lerpf(start.y, finish.y, u) + open_wave, blend) + restless
            var current := Vector2(x, y)
            if pointer_active and not preview_mode:
                var distance := current.distance_to(pointer)
                if distance < 155.0:
                    current += (current - pointer).normalized() * (155.0 - distance) * 0.35
            pts.append(current)
        var shade := BLUE_LIGHT.lerp(WARM, blend * (0.28 + 0.40 * spread))
        shade.a = 0.16 + (0.32 + 0.16 * blend) * (0.5 + 0.5 * sin(index * 0.41 + t * 0.18))
        draw_polyline(pts, shade, 1.3 + 0.6 * blend, true)
        if i % 7 == 0:
            var bright := PALE.lerp(WARM, 0.7 * blend)
            bright.a = 0.12 + blend * 0.22
            draw_polyline(pts, bright, 0.72, true)

func _draw_center(t: float) -> void:
    var center := Vector2(640.0, 360.0)
    var anxiety := 1.0 - blend
    for ring in range(5):
        var radius := 17.0 + float(ring) * 13.0 + blend * float(ring) * 7.0
        var alpha := (0.25 - float(ring) * 0.045) * (0.45 + blend * 0.55)
        var colour := PALE.lerp(WARM, blend * 0.83)
        colour.a = alpha
        draw_arc(center, radius, -PI * 0.7 + sin(t * 0.12) * 0.1, PI * (0.9 + blend * 0.47), 96, colour, 1.25, true)
    var heart := PALE.lerp(WARM, blend)
    heart.a = 0.38 + blend * 0.42
    draw_circle(center, 3.4 + anxiety * 1.4 + sin(t * 0.55) * 0.3, heart)