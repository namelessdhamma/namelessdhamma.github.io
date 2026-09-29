extends CanvasLayer

var panel: PanelContainer
var result_label: Label
var hit_button: Button
var hold_button: Button

func _ready() -> void:
	_build_surface()
	var pirate_button := get_parent().get_node("SafeArea/Landscape/Center/WorldStrip/Pirate") as Button
	pirate_button.pressed.connect(show_opening_choice)
	panel.visible = false

func _build_surface() -> void:
	panel = PanelContainer.new()
	panel.name = "PirateOpeningChoice"
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(420, 220)
	panel.position = Vector2(-210, -110)
	add_child(panel)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	panel.add_child(column)

	var title := Label.new()
	title.text = "РИФЫ!"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(title)

	var prompt := Label.new()
	prompt.text = "Бармалей теряет равновесие. Штурвал рядом."
	prompt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	prompt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(prompt)

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

func show_opening_choice() -> void:
	PirateOpeningCampaign.reset()
	result_label.text = ""
	hit_button.disabled = false
	hold_button.disabled = false
	panel.visible = true
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
		panel.visible = false
		get_viewport().set_input_as_handled()
