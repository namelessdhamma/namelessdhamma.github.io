shader_type canvas_item;
render_mode unshaded;

uniform sampler2D source_texture : source_color;
uniform float anim_time = 0.0;
uniform float progress = 0.0;
uniform float lightning_flash = 0.0;

void fragment() {
	float t = anim_time;
	vec2 uv = UV;

	float upper = 1.0 - smoothstep(0.52, 0.76, uv.y);
	float central_sails = smoothstep(0.04, 0.22, uv.x) * (1.0 - smoothstep(0.83, 0.98, uv.x));
	float sail_mask = upper * central_sails;

	float gust = sin(t * 2.15 + uv.y * 19.0) + 0.45 * sin(t * 4.6 + uv.x * 31.0);
	uv.x += sail_mask * gust * 0.0065;
	uv.y += sail_mask * sin(t * 2.8 + uv.x * 23.0) * 0.0028;

	vec4 c = texture(source_texture, clamp(uv, vec2(0.002), vec2(0.998)));

	float warm = smoothstep(0.10, 0.52, c.r - c.b) * smoothstep(0.06, 0.42, c.r);
	float lantern_flicker = 0.86 + 0.14 * sin(t * 8.3) * sin(t * 3.1 + 1.2);
	c.rgb += vec3(0.30, 0.105, 0.015) * warm * lantern_flicker * 0.42;

	c.rgb += vec3(0.50, 0.66, 0.92) * lightning_flash * c.a * 0.78;
	COLOR = c;
}
