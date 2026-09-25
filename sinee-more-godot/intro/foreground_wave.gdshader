shader_type canvas_item;
render_mode unshaded;

uniform float anim_time = 0.0;
uniform float progress = 0.0;
uniform float lightning_flash = 0.0;

float hash21(vec2 p) {
	return fract(sin(dot(p, vec2(41.7, 289.3))) * 43758.5453);
}

void fragment() {
	float t = anim_time;
	vec2 uv = UV;

	float h1 = 0.79 + 0.035 * sin(uv.x * 12.0 - t * 1.85) + 0.016 * sin(uv.x * 29.0 + t * 2.9);
	float h2 = 0.90 + 0.022 * sin(uv.x * 18.0 + t * 2.35 + 1.3);

	float crest1 = 1.0 - smoothstep(0.0, 0.018, abs(uv.y - h1));
	float crest2 = 1.0 - smoothstep(0.0, 0.013, abs(uv.y - h2));
	float body = smoothstep(h1 - 0.03, h1 + 0.09, uv.y);

	float foam_noise = 0.55 + 0.45 * sin(uv.x * 77.0 - t * 5.8 + uv.y * 21.0);
	float foam = (crest1 * 0.85 + crest2 * 0.65) * foam_noise;

	vec2 cells = floor(vec2(uv.x * 110.0 + t * 5.0, uv.y * 70.0 - t * 2.0));
	float spray_rand = hash21(cells);
	float spray_band = smoothstep(0.56, 0.82, uv.y) * (1.0 - smoothstep(0.88, 0.98, uv.y));
	float spray = step(0.972, spray_rand) * spray_band;

	vec3 water = vec3(0.015, 0.060, 0.090) * body * 0.30;
	vec3 foam_col = vec3(0.62, 0.78, 0.94) * foam * 0.42;
	vec3 flash = vec3(0.55, 0.70, 0.96) * lightning_flash * (foam * 0.45 + spray * 0.7);
	float alpha = clamp(body * 0.10 + foam * 0.28 + spray * 0.36, 0.0, 0.50);

	COLOR = vec4(water + foam_col + flash, alpha);
}
