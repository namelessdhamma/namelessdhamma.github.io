shader_type canvas_item;
render_mode unshaded;

uniform float anim_time = 0.0;
uniform float intensity = 1.0;

float hash21(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float layer(vec2 uv, float cells_x, float cells_y, float speed, float slant, float threshold, float width) {
	vec2 p = uv;
	p.y += anim_time * speed;
	p.x += anim_time * speed * 0.23;
	vec2 g = vec2(p.x * cells_x - p.y * slant, p.y * cells_y);
	vec2 id = floor(g);
	vec2 f = fract(g);
	float rnd = hash21(id);
	float streak = 1.0 - smoothstep(width, width * 3.2, abs(f.x - 0.5));
	float length_mask = smoothstep(0.02, 0.14, f.y) * (1.0 - smoothstep(0.62, 0.98, f.y));
	return streak * length_mask * step(threshold, rnd);
}

void fragment() {
	float far_rain = layer(UV + vec2(0.11, 0.06), 145.0, 68.0, 2.25, 39.0, 0.84, 0.012);
	float mid_rain = layer(UV + vec2(0.31, 0.17), 96.0, 44.0, 1.72, 25.0, 0.77, 0.014);
	float near_rain = layer(UV + vec2(0.53, 0.29), 58.0, 28.0, 1.24, 16.0, 0.70, 0.017);

	float streak = far_rain * 0.34 + mid_rain * 0.52 + near_rain * 0.78;
	float mist = smoothstep(0.60, 1.0, UV.y) * (0.022 + 0.018 * (0.5 + 0.5 * sin(UV.x * 31.0 + anim_time * 1.7)));
	float alpha = clamp(streak * 0.62 * intensity + mist, 0.0, 0.72);
	COLOR = vec4(0.68, 0.80, 0.94, alpha);
}
