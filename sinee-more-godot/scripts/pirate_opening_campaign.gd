extends Node

const CONTRACT_PATH := "res://campaign/pirate_sea/opening_reefs_choice.json"

var contract: Dictionary = {}
var current_choice := ""
var outcome: Dictionary = {}

func _ready() -> void:
	_load_contract()
	if DisplayServer.get_name() == "headless":
		_run_contract_smoke()

func _load_contract() -> void:
	var file := FileAccess.open(CONTRACT_PATH, FileAccess.READ)
	assert(file != null, "Pirate Sea opening contract is missing")
	var parsed = JSON.parse_string(file.get_as_text())
	assert(parsed is Dictionary, "Pirate Sea opening contract must be a JSON object")
	contract = parsed
	assert(contract.get("id", "") == "pirate_sea_opening_reefs_choice")
	assert(contract.get("presentation", {}).get("player_facing_stats", true) == false)

func available_choices() -> Array:
	return contract.get("choice", {}).get("options", [])

func choose(choice_id: String) -> Dictionary:
	for option in available_choices():
		if option.get("id", "") == choice_id:
			current_choice = choice_id
			outcome = option.get("consequence", {}).duplicate(true)
			return outcome.duplicate(true)
	push_error("Unknown Pirate Sea opening choice: %s" % choice_id)
	return {}

func reset() -> void:
	current_choice = ""
	outcome = {}

func _run_contract_smoke() -> void:
	var hit := choose("hit_wheel")
	assert(hit.get("silas_kills_barmaley") == true)
	assert(hit.get("silas_worsens_ship_position") == true)
	assert(hit.get("barmaley_fate") == "mortally_wounded_then_swept_overboard")
	reset()
	var hold := choose("hold")
	assert(hold.get("silas_kills_barmaley") == false)
	assert(hold.get("silas_worsens_ship_position") == false)
	assert(hold.get("barmaley_fate") == "swept_overboard_alive_unknown")
	assert(not contract.get("presentation", {}).get("player_facing_stats", true))
	print("BLUE_SEA_PIRATE_OPENING_BRANCH_PASS choices=hit_wheel,hold stats=hidden")
