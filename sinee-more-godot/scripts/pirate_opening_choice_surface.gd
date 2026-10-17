extends CanvasLayer

var panel: PanelContainer
var result_label: Label
var hit_button: Button
var hold_button: Button
var close_button: Button
var title_label: Label
var prompt_label: Label
var column: VBoxContainer
var shell: VBoxContainer
var narrative_scroll: ScrollContainer

func _ready() -> void:
	_build_surface()
	var pirate_button := get_parent().get_node("SafeArea/Landscape/Center/WorldStrip/Pirate") as Button
	pirate_button.pressed.connect(show_opening_choice)
	panel.visible = false

func _build_surface() -> void:
	panel = PanelContainer.new()
	panel.name = "PirateOpeningChoice"
	panel.set_anchors_preset(Control.PRESET_CENTER)
	add_child(panel)

	# Keep the close control OUTSIDE the scrollable story so it can never
	# disappear below long Russian text at a 746x280 phone viewport.
	shell = VBoxContainer.new()
	shell.name = "Shell"
	shell.add_theme_constant_override("separation", 4)
	panel.add_child(shell)
	var header := HBoxContainer.new()
	header.name = "Header"
	shell.add_child(header)
	title_label = Label.new()
	title_label.text = "РИФЫ!"
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	header.add_child(title_label)
	close_button = Button.new()
	close_button.name = "CloseButton"
	close_button.text = "ЗАКРЫТЬ"
	close_button.pressed.connect(_close_surface)
	header.add_child(close_button)

	narrative_scroll = ScrollContainer.new()
	narrative_scroll.name = "StoryScroll"
	narrative_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	narrative_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	shell.add_child(narrative_scroll)
	column = VBoxContainer.new()
	column.name = "Column"
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 8)
	narrative_scroll.add_child(column)

	prompt_label = Label.new()
	prompt_label.text = "Бармалей теряет равновесие. Штурвал рядом."
	prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	prompt_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(prompt_label)

	hit_button = Button.new()
	hit_button.text = "УДАРИТЬ ПО РУЛЮ"
	hit_button.custom_minimum_size = Vector2(0, 44)
	hit_button.pressed.connect(_choose.bind("hit_wheel"))
	column.add_child(hit_button)

	hold_button = Button.new()
	hold_button.text = "НЕ ТРОГАТЬ РУЛЬ"
	hold_button.custom_minimum_size = Vector2(0, 44)
	hold_button.pressed.connect(_choose.bind("hold"))
	column.add_child(hold_button)

	result_label = Label.new()
	result_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	result_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(result_label)

	get_viewport().size_changed.connect(_update_mobile_layout)
	call_deferred("_update_mobile_layout")

func _update_mobile_layout() -> void:
	if panel == null:
		return
	var viewport_size := get_viewport().get_visible_rect().size
	var physical_height := get_window().size.y
	if viewport_size.x <= 0.0 or viewport_size.y <= 0.0 or physical_height <= 0:
		return
	var scale := maxf(0.01, float(physical_height) / viewport_size.y)
	var logical_touch := ceilf(44.0 / scale)
	var logical_font := maxi(16, ceili(14.0 / scale))
	for button in [hit_button, hold_button, close_button]:
		button.custom_minimum_size = Vector2(0, logical_touch)
		button.add_theme_font_size_override("font_size", logical_font)
	# The close button is pinned in the header; the narrative and choices
	# scroll independently when their combined minimum exceeds the panel.
	close_button.custom_minimum_size.x = maxf(120.0, 100.0 / scale)
	for label in [title_label, prompt_label, result_label]:
		label.add_theme_font_size_override("font_size", logical_font)
	# Reserve 3 equally accessible touch targets plus narrative text.
	var panel_width := minf(viewport_size.x * 0.88, maxf(420.0, 760.0 / scale))
	var panel_height := minf(viewport_size.y * 0.94, maxf(380.0, 3.0 * logical_touch + 4.5 * logical_font + 80.0))
	panel.custom_minimum_size = Vector2(panel_width, panel_height)
	# Reserve room for the always-visible close header and scroll the rest.
	narrative_scroll.custom_minimum_size = Vector2(0.0, 0.0)
	panel.anchor_left = 0.5
	panel.anchor_right = 0.5
	panel.anchor_top = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -panel_width * 0.5
	panel.offset_right = panel_width * 0.5
	panel.offset_top = -panel_height * 0.5
	panel.offset_bottom = panel_height * 0.5

func _close_surface() -> void:
	panel.visible = false
	# Restore keyboard focus without requiring a physical Escape key.
	var menu := get_parent().get_node_or_null("SafeArea/Landscape/Center/TopBar/GameMenu") as Control
	if menu != null:
		menu.grab_focus()

func show_opening_choice() -> void:
	_update_mobile_layout()
	PirateOpeningCampaign.reset()
	result_label.text = ""
	hit_button.disabled = false
	hold_button.disabled = false
	panel.visible = true
	narrative_scroll.scroll_vertical = 0
	hit_button.grab_focus()

func _choose(choice_id: String) -> void:
	var outcome := PirateOpeningCampaign.choose(choice_id)
	assert(not outcome.is_empty(), "Pirate opening choice must resolve")
	hit_button.disabled = true
	hold_button.disabled = true
	if choice_id == "hit_wheel":
		result_label.text = "Сайлас бьёт по рулю. Бармалей смертельно ранен."
	else:
		result_label.text = "Сайлас не трогает руль. Корабль ударяется о риф; Бармалея смывает живым."
	print("BLUE_SEA_PIRATE_OPENING_PRESENTATION_PASS choice=", choice_id, " outcome=", outcome)

func _unhandled_key_input(event: InputEvent) -> void:
	if not panel.visible or not event.pressed or event.echo:
		return
	if event.keycode == KEY_ESCAPE:
		_close_surface()
		get_viewport().set_input_as_handled()
