shader_type canvas_item;
render_mode unshaded;

uniform float anim_time = 0.0;
uniform int shot_a = 0;
uniform int shot_b = 1;
uniform float mix_amount = 0.0;
uniform float lightning_flash = 0.0;
uniform sampler2D atlas_texture : source_color;

vec2 ship_center(int idx) {
	if (idx == 2) return vec2(0.67, 0.50);
	if (idx == 3) return vec2(0.53, 0.53);
	if (idx == 4) return vec2(0.54, 0.51);
	if (idx == 5) return vec2(0.52, 0.52);
	if (idx == 6) return vec2(0.50, 0.54);
	if (idx == 7) return vec2(0.50, 0.55);
	if (idx == 8) return vec2(0.50, 0.52);
	return vec2(0.50, 0.55);
}

vec2 ship_extent(int idx) {
	if (idx == 2) return vec2(0.23, 0.25);
	if (idx == 3) return vec2(0.36, 0.35);
	if (idx == 4) return vec2(0.48, 0.42);
	if (idx == 5) return vec2(0.70, 0.54);
	if (idx == 6) return vec2(0.78, 0.60);
	if (idx == 7) return vec2(0.82, 0.64);
	if (idx == 8) return vec2(0.80, 0.60);
	return vec2(0.20, 0.20);
}

vec4 animated_shot(int idx, vec2 base_uv) {
	vec2 uv = base_uv;
	float fi = float(idx);
	float t = anim_time;

	float cam_angle = sin(t * 0.42 + fi * 0.71) * 0.0065;
	float ca = cos(cam_angle);
	float sa = sin(cam_angle);
	vec2 centered = uv - vec2(0.5);
	uv = mat2(vec2(ca, -sa), vec2(sa, ca)) * centered + vec2(0.5);
	float zoom = 1.025 + 0.010 * sin(t * 0.33 + fi);
	uv = vec2(0.5) + (uv - vec2(0.5)) / zoom;
	uv += vec2(sin(t * 0.19 + fi) * 0.0025, cos(t * 0.23 + fi) * 0.0018);

	float water = smoothstep(0.43, 0.93, uv.y);
	float swell = sin(uv.x * 18.0 + t * 1.15 + fi) + 0.55 * sin(uv.x * 39.0 - t * 1.72);
	float chop = sin(uv.x * 73.0 + uv.y * 19.0 + t * 2.8);
	uv.x += water * (0.0042 * sin(uv.y * 41.0 + t * 1.35) + 0.0016 * chop);
	uv.y += water * (0.0048 * swell + 0.0018 * chop);

	float ship_mask = 0.0;
	if (idx >= 2) {
		vec2 ctr = ship_center(idx);
		vec2 ext = ship_extent(idx);
		float d = length((uv - ctr) / ext);
		ship_mask = 1.0 - smoothstep(0.72, 1.05, d);
		float rock_amp = idx < 5 ? 0.014 : 0.0075;
		float rock = sin(t * 1.05 + fi * 0.67) * rock_amp;
		float cr = cos(-rock);
		float sr = sin(-rock);
		vec2 q = uv - ctr;
		vec2 rocked = mat2(vec2(cr, -sr), vec2(sr, cr)) * q + ctr;
		rocked.y += sin(t * 1.42 + fi * 0.9) * (idx < 5 ? 0.0065 : 0.0040);
		uv = mix(uv, rocked, ship_mask * 0.88);

		float upper = 1.0 - smoothstep(0.36, 0.69, uv.y);
		float sail = ship_mask * upper;
		uv.x += sail * (0.0038 * sin(t * 2.25 + uv.y * 24.0 + fi) + 0.0018 * sin(t * 3.9 + uv.x * 31.0));
		uv.y += sail * 0.0018 * sin(t * 2.7 + uv.x * 27.0);
	}

	float sky = 1.0 - smoothstep(0.30, 0.62, uv.y);
	uv.x += sky * 0.0026 * sin(t * 0.37 + uv.y * 9.0 + fi);
	uv = clamp(uv, vec2(0.002), vec2(0.998));

	int col_i = idx % 3;
	int row_i = idx / 3;
	vec2 atlas_uv = (uv + vec2(float(col_i), float(row_i))) / 3.0;
	vec4 c = texture(atlas_texture, atlas_uv);

	float foam = water * (0.5 + 0.5 * sin(base_uv.x * 115.0 + base_uv.y * 24.0 - t * 5.2));
	foam *= 0.5 + 0.5 * sin(base_uv.x * 57.0 + t * 3.1);
	c.rgb += vec3(0.035, 0.050, 0.070) * foam;
	c.rgb *= 0.985 + 0.018 * sin(t * 0.55 + fi * 0.4);
	return c;
}

void fragment() {
	vec4 a = animated_shot(shot_a, UV);
	vec4 b = animated_shot(shot_b, UV);
	float m = smoothstep(0.0, 1.0, mix_amount);
	vec4 c = mix(a, b, m);
	c.rgb += vec3(0.52, 0.66, 0.90) * lightning_flash * 0.58;
	float vignette = 1.0 - smoothstep(0.40, 0.78, length(UV - vec2(0.5)));
	c.rgb *= 0.72 + 0.28 * vignette;
	COLOR = c;
}
