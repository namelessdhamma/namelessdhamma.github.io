shader_type canvas_item;
render_mode unshaded;

uniform sampler2D source_texture : source_color;
uniform float anim_time = 0.0;
uniform float progress = 0.0;
uniform float lightning_flash = 0.0;

float ease_in_out(float x) {
	return x * x * (3.0 - 2.0 * x);
}

void fragment() {
	float t = anim_time;
	float p = ease_in_out(clamp(progress, 0.0, 1.0));

	float zoom = mix(1.0, 1.48, p);
	vec2 focus = mix(vec2(0.5, 0.5), vec2(0.665, 0.505), p * 0.76);
	vec2 uv = focus + (UV - vec2(0.5)) / zoom;

	float sky_mask = 1.0 - smoothstep(0.30, 0.52, uv.y);
	float water_mask = smoothstep(0.43, 0.94, uv.y);

	uv.x += sky_mask * (0.0060 * sin(t * 0.20 + uv.y * 7.0) + 0.0020 * sin(t * 0.49 + uv.y * 17.0));

	float swell_a = sin(uv.x * 15.0 - t * 1.15 + uv.y * 5.0);
	float swell_b = sin(uv.x * 31.0 + t * 1.72 - uv.y * 8.0);
	float swell_c = sin(uv.x * 63.0 - t * 2.55 + uv.y * 19.0);
	float depth_gain = smoothstep(0.44, 1.0, uv.y);

	uv.y += water_mask * depth_gain * (0.0105 * swell_a + 0.0045 * swell_b + 0.0022 * swell_c);
	uv.x += water_mask * depth_gain * (0.0068 * sin(uv.y * 38.0 + t * 1.35) + 0.0027 * swell_c);

	uv = clamp(uv, vec2(0.002), vec2(0.998));
	vec4 c = texture(source_texture, uv);

	float crest_a = 0.5 + 0.5 * sin(UV.x * 47.0 - t * 4.6 + UV.y * 17.0);
	float crest_b = 0.5 + 0.5 * sin(UV.x * 83.0 + t * 6.1 - UV.y * 29.0);
	float moving_foam = pow(max(crest_a * crest_b, 0.0), 5.0) * smoothstep(0.50, 0.96, UV.y);
	c.rgb += vec3(0.075, 0.105, 0.135) * moving_foam;

	float cold_flash = lightning_flash * (0.55 + 0.45 * sky_mask);
	c.rgb += vec3(0.52, 0.67, 0.92) * cold_flash * 0.68;

	float vignette = 1.0 - smoothstep(0.42, 0.78, length(UV - vec2(0.5)));
	c.rgb *= 0.72 + 0.28 * vignette;

	COLOR = c;
}
