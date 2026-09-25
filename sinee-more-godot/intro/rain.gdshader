shader_type canvas_item;
render_mode unshaded;

uniform float intensity = 1.0;

float hash21(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float rain_layer(vec2 uv, float cells_x, float cells_y, float speed, float slant, float threshold) {
	vec2 p = uv;
	p.y += TIME * speed;
	p.x += TIME * speed * 0.28;
	vec2 g = vec2(p.x * cells_x - p.y * slant, p.y * cells_y);
	vec2 id = floor(g);
	vec2 f = fract(g);
	float rnd = hash21(id);
	float thin = 1.0 - smoothstep(0.018, 0.075, abs(f.x - 0.5));
	float length_mask = smoothstep(0.03, 0.20, f.y) * (1.0 - smoothstep(0.70, 0.98, f.y));
	return thin * length_mask * step(threshold, rnd);
}

void fragment() {
	float near_rain = rain_layer(UV, 72.0, 31.0, 1.55, 18.0, 0.73);
	float far_rain = rain_layer(UV + vec2(0.17, 0.09), 118.0, 54.0, 2.25, 30.0, 0.80);
	float fine_rain = rain_layer(UV + vec2(0.37, 0.21), 164.0, 74.0, 2.85, 42.0, 0.87);
	float streak = near_rain * 0.72 + far_rain * 0.46 + fine_rain * 0.28;
	float mist = smoothstep(0.62, 1.0, UV.y) * (0.025 + 0.018 * sin(UV.x * 22.0 + TIME * 1.4));
	float alpha = clamp(streak * 0.58 * intensity + mist, 0.0, 0.62);
	COLOR = vec4(0.66, 0.79, 0.92, alpha);
}
